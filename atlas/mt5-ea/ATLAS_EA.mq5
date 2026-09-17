//+------------------------------------------------------------------+
//| ATLAS_EA.mq5                                                     |
//| Autonomous Trading Logic and Analysis System                     |
//| TJR EUR/USD London Session — MT5 Bridge EA                       |
//|                                                                  |
//| Merges:                                                          |
//|   APEX2_Bridge.mq5       → candle push (JOB 1)                  |
//|   APEX_Trade_Recieve.mq5 → signal poll + execution (JOB 2)      |
//|   New: manage poll        → partial close / SL / exit (JOB 3)   |
//|                                                                  |
//| Transport: HTTP WebRequest ONLY                                  |
//|            NO ZeroMQ, NO DLL imports                             |
//| Magic number: 20240101                                           |
//|                                                                  |
//| Signal format (pipe-delimited, 7 fields):                        |
//|   ACTION|LOT|SL|TP1|TP2|TP3|TRADE_ID                           |
//|   e.g. SELL|0.09|1.08520|1.08340|1.08230|1.08050|uuid-abc123   |
//|                                                                  |
//| Manage format (pipe-delimited):                                  |
//|   PARTIAL_CLOSE|PCT|TRADE_ID                                     |
//|   MODIFY_SL|NEW_SL_PRICE|TRADE_ID                               |
//|   CLOSE_ALL|REASON|TRADE_ID                                      |
//+------------------------------------------------------------------+
#property copyright "ATLAS System"
#property version   "2.00"
#property strict

#include <Trade\Trade.mqh>

CTrade trade;

//--- Endpoints (port 3001 must be whitelisted in Tools → Options → Expert Advisors)
string CANDLE_URL = "http://127.0.0.1:3001/mt5/candles";
string SIGNAL_URL = "http://127.0.0.1:3001/signal";
string MANAGE_URL = "http://127.0.0.1:3001/manage";
string ACK_URL    = "http://127.0.0.1:3001/mt5/ack";

//--- ATLAS magic number — identifies all positions opened by this EA
int MAGIC = 20240101;

//--- Trade state: persists across OnTimer() calls
string last_executed_id = "";   // idempotency guard — skip already-executed signal IDs
ulong  open_ticket      = 0;    // MT5 position ticket; 0 = no open ATLAS trade
string open_trade_id    = "";   // ATLAS backend trade UUID
double open_lot         = 0.0;  // original full lot size at entry (for partial close calc)
double g_tp1            = 0.0;  // TP1 = midpoint of Asia range (40% close)
double g_tp2            = 0.0;  // TP2 = opposing Asia level (35% close)
double g_tp3            = 0.0;  // TP3 = HTF DOL runner (25% remainder)

//--- Bar-open timestamps for new-bar detection (oldest candle[0] open time)
datetime lastBarM5  = 0;
datetime lastBarH4  = 0;
datetime lastBarD1  = 0;

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(MAGIC);
   trade.SetDeviationInPoints(10);        // max 1 pip slippage tolerance
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   //--- 1-second timer drives all three jobs
   EventSetTimer(1);

   //--- Push all timeframes immediately so backend has data before first bar close
   PushAllTimeframes();

   Print("ATLAS EA v2.00 initialised | Magic=", MAGIC,
         " | Candle push: active | Signal poll: active | Manage poll: active");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| OnDeinit                                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("ATLAS EA stopped | Reason=", reason);
}

//+------------------------------------------------------------------+
//| OnTick — intentionally empty; all logic is timer-driven          |
//+------------------------------------------------------------------+
void OnTick() {}

//+------------------------------------------------------------------+
//| OnTimer — fires every second                                     |
//| JOB 1: push candles on new bar (not every second)               |
//| JOB 2: poll /signal when no open position                        |
//| JOB 3: poll /manage when a position is open                      |
//+------------------------------------------------------------------+
void OnTimer()
{
   //================================================================
   // JOB 1 — CANDLE PUSH
   // Triggered only when a new bar opens, not every second.
   // M5 + M15: pushed on every new M5 bar (80 candles each).
   //   M15 data is included on every M5 push so the backend always
   //   has fresh 15M structure for CHoCH detection (Section 3.4a).
   // H4 + GBPUSD H1: pushed on new H4 bar (50 candles).
   //   GBPUSD H1 pushed alongside H4 for SMT divergence context.
   // D1: pushed on new D1 bar (30 candles) for Daily DOL (Rule 3.1).
   //================================================================
   datetime curBarM5 = iTime("EURUSD", PERIOD_M5, 0);
   datetime curBarH4 = iTime("EURUSD", PERIOD_H4, 0);
   datetime curBarD1 = iTime("EURUSD", PERIOD_D1, 0);

   if(curBarM5 != lastBarM5)
   {
      lastBarM5 = curBarM5;
      //--- M5: 300 candles — covers ~25 hours of M5 data.
      //    Asia range window is 20:00–00:00 EST = 240 bars; 300 guarantees the full
      //    Asia session is always present in the signal-engine buffer even if the
      //    EA or backend restarts during the London session (08:00–12:00 UTC).
      PushCandles("EURUSD", PERIOD_M5,  "5min",  300);
      //--- M15: 80 candles — covers ~20 hours for 15M CHoCH detection (Rule 3.4a)
      PushCandles("EURUSD", PERIOD_M15, "15min", 80);
   }

   if(curBarH4 != lastBarH4)
   {
      lastBarH4 = curBarH4;
      //--- H4: 50 candles — covers ~8 days for 4H structural context (Rule 3.2)
      PushCandles("EURUSD", PERIOD_H4, "4h",   50);
      //--- GBPUSD H1: 50 candles — SMT divergence context alongside H4 push
      PushCandles("GBPUSD", PERIOD_H1, "1h",   50);
   }

   if(curBarD1 != lastBarD1)
   {
      lastBarD1 = curBarD1;
      //--- D1: 30 candles — Daily DOL identification (Rules 3.1a/3.1b)
      PushCandles("EURUSD", PERIOD_D1, "1day", 30);
   }

   //================================================================
   // JOB 2 — SIGNAL POLL
   // Only runs when no ATLAS position is open (open_ticket == 0).
   // Polls GET /signal. Backend returns pipe-delimited string or
   // "null" when no signal is ready.
   // Idempotency: last_executed_id prevents re-executing the same
   // signal if the backend hasn't cleared it yet.
   //================================================================
   if(open_ticket == 0)
   {
      PollSignal();
   }

   //================================================================
   // JOB 3 — MANAGE POLL
   // Only runs when an ATLAS position is open (open_ticket > 0).
   // Handles: PARTIAL_CLOSE (TP1/TP2), MODIFY_SL (break-even,
   // trailing), CLOSE_ALL (invalidation exits, time kills).
   //================================================================
   if(open_ticket > 0)
   {
      PollManage();
   }
}

//+------------------------------------------------------------------+
//| JOB 2 IMPLEMENTATION — Signal poll and trade execution           |
//+------------------------------------------------------------------+
void PollSignal()
{
   string data = HttpGet(SIGNAL_URL);
   if(data == "" || data == "null") return;

   //--- Parse pipe-delimited signal: ACTION|LOT|SL|TP1|TP2|TP3|TRADE_ID
   string parts[];
   int count = StringSplit(data, '|', parts);

   if(count < 7)
   {
      Print("ATLAS signal parse error — expected 7 fields, got ", count, " | raw=", data);
      return;
   }

   string action   = parts[0];   // "BUY" or "SELL"
   double lot      = StringToDouble(parts[1]);
   double sl       = StringToDouble(parts[2]);
   double tp1      = StringToDouble(parts[3]);  // TP1: Asia range midpoint (Rule 6.2)
   double tp2      = StringToDouble(parts[4]);  // TP2: opposing Asia level (Rule 6.3)
   double tp3      = StringToDouble(parts[5]);  // TP3: HTF DOL (Rule 6.4)
   string trade_id = parts[6];

   //--- Field validation
   if(lot  <= 0) { Print("ATLAS: invalid lot=",  lot,  " | signal=", data); return; }
   if(sl   <= 0) { Print("ATLAS: invalid sl=",   sl,   " | signal=", data); return; }
   if(tp1  <= 0) { Print("ATLAS: invalid tp1=",  tp1,  " | signal=", data); return; }
   if(StringLen(trade_id) == 0) { Print("ATLAS: empty trade_id | signal=", data); return; }

   //--- Idempotency guard: skip if this signal was already executed
   if(trade_id == last_executed_id)
   {
      return;  // backend hasn't cleared yet; silently skip
   }

   //--- Validate action string
   if(action != "BUY" && action != "SELL")
   {
      Print("ATLAS: unknown action=", action, " | signal=", data);
      return;
   }

   Print("ATLAS executing signal | ", action, " lot=", lot,
         " sl=", sl, " tp1=", tp1, " tp2=", tp2, " tp3=", tp3,
         " id=", trade_id);

   //--- Execute trade
   //    MT5 order uses TP1 as the hard take-profit on the broker side.
   //    TP2 and TP3 are managed in software via JOB 3 partial closes.
   bool ok = false;
   if(action == "BUY")
      ok = trade.Buy(lot, "EURUSD", 0, sl, tp1, "ATLAS_" + trade_id);
   else
      ok = trade.Sell(lot, "EURUSD", 0, sl, tp1, "ATLAS_" + trade_id);

   if(ok && trade.ResultRetcode() == TRADE_RETCODE_DONE)
   {
      open_ticket    = trade.ResultOrder();
      open_trade_id  = trade_id;
      open_lot       = lot;
      g_tp1          = tp1;
      g_tp2          = tp2;
      g_tp3          = tp3;
      last_executed_id = trade_id;

      Print("ATLAS trade OPEN | ticket=", open_ticket,
            " price=", trade.ResultPrice(),
            " id=", trade_id);

      PostAck("OPEN_ACK", trade_id, open_ticket,
              "OK", trade.ResultPrice(), 0, "Trade opened");
   }
   else
   {
      int err = (int)trade.ResultRetcode();
      Print("ATLAS trade FAILED | retcode=", err,
            " comment=", trade.ResultComment(),
            " id=", trade_id);

      PostAck("OPEN_ACK", trade_id, 0,
              "ERROR", 0, err, trade.ResultComment());
   }
}

//+------------------------------------------------------------------+
//| JOB 3 IMPLEMENTATION — Manage poll (partial close / SL / exit)  |
//+------------------------------------------------------------------+
void PollManage()
{
   //--- Verify position still exists; if not, reset state and return
   if(!PositionSelectByTicket(open_ticket))
   {
      Print("ATLAS: position ", open_ticket, " no longer exists — resetting state");
      open_ticket   = 0;
      open_trade_id = "";
      open_lot      = 0.0;
      return;
   }

   //--- Poll backend for management command
   string url  = MANAGE_URL + "?ticket=" + IntegerToString((long)open_ticket);
   string data = HttpGet(url);
   if(data == "" || data == "null") return;

   //--- Parse pipe-delimited command
   string parts[];
   int count = StringSplit(data, '|', parts);
   if(count < 1) return;

   string cmd = parts[0];

   //--- PARTIAL_CLOSE|PCT|TRADE_ID
   //    Implements Rule 6.2c (40% close at TP1) and Rule 6.3a/6.3b (35% close at TP2)
   if(cmd == "PARTIAL_CLOSE")
   {
      if(count < 2) { Print("ATLAS PARTIAL_CLOSE: missing PCT field"); return; }
      double pct       = StringToDouble(parts[1]);
      double closeLots = NormalizeDouble(open_lot * pct / 100.0, 2);

      //--- Enforce broker minimum lot (0.01 for most brokers)
      double minLot = SymbolInfoDouble("EURUSD", SYMBOL_VOLUME_MIN);
      if(closeLots < minLot) closeLots = minLot;

      //--- Do not attempt to close more than the position volume
      double posVol = PositionGetDouble(POSITION_VOLUME);
      if(closeLots > posVol) closeLots = posVol;

      Print("ATLAS PARTIAL_CLOSE ", pct, "% | closing ", closeLots,
            " lots of ", posVol, " | ticket=", open_ticket);

      bool ok = trade.PositionClosePartial(open_ticket, closeLots);
      double closePrice = trade.ResultPrice();
      int    retcode    = (int)trade.ResultRetcode();

      PostAck("MANAGE_ACK", open_trade_id, open_ticket,
              ok ? "PARTIAL_CLOSE_OK" : "PARTIAL_CLOSE_ERROR",
              closePrice, retcode, trade.ResultComment());
      return;
   }

   //--- MODIFY_SL|NEW_SL_PRICE|TRADE_ID
   //    Implements Rule 5.4 (break-even trigger) and Rule 6.4b (trailing stop)
   if(cmd == "MODIFY_SL")
   {
      if(count < 2) { Print("ATLAS MODIFY_SL: missing price field"); return; }
      double newSL = StringToDouble(parts[1]);
      if(newSL <= 0) { Print("ATLAS MODIFY_SL: invalid price=", newSL); return; }

      //--- PositionModify: pass 0 for TP to leave existing TP1 unchanged on broker side
      double currentTP = PositionGetDouble(POSITION_TP);
      bool ok = trade.PositionModify(open_ticket, newSL, currentTP);
      int  retcode = (int)trade.ResultRetcode();

      Print("ATLAS MODIFY_SL | new_sl=", newSL,
            " ok=", ok, " retcode=", retcode,
            " ticket=", open_ticket);

      PostAck("MANAGE_ACK", open_trade_id, open_ticket,
              ok ? "MODIFY_SL_OK" : "MODIFY_SL_ERROR",
              newSL, retcode, trade.ResultComment());
      return;
   }

   //--- CLOSE_ALL|REASON|TRADE_ID
   //    Implements Section 8.2 mid-trade invalidation exits and Rule 8.2.4 time kill
   if(cmd == "CLOSE_ALL")
   {
      string reason = (count >= 2) ? parts[1] : "UNSPECIFIED";
      Print("ATLAS CLOSE_ALL | reason=", reason, " | ticket=", open_ticket);

      bool ok = trade.PositionClose(open_ticket);
      double closePrice = trade.ResultPrice();
      int    retcode    = (int)trade.ResultRetcode();

      PostAck("MANAGE_ACK", open_trade_id, open_ticket,
              ok ? "CLOSE_ALL_OK" : "CLOSE_ALL_ERROR",
              closePrice, retcode, reason);

      if(ok)
      {
         //--- Reset all trade state
         open_ticket   = 0;
         open_trade_id = "";
         open_lot      = 0.0;
         g_tp1 = 0.0; g_tp2 = 0.0; g_tp3 = 0.0;
         Print("ATLAS position closed | reason=", reason);
      }
      return;
   }

   Print("ATLAS: unknown manage command=", cmd, " | raw=", data);
}

//+------------------------------------------------------------------+
//| Push all timeframes to backend (called on OnInit)                |
//+------------------------------------------------------------------+
void PushAllTimeframes()
{
   //--- EUR/USD: M5 and M15 for LKZ structure
   PushCandles("EURUSD", PERIOD_M5,  "5min",  300);
   PushCandles("EURUSD", PERIOD_M15, "15min", 80);
   //--- EUR/USD: H4 for 4H structure context (Rule 3.2)
   PushCandles("EURUSD", PERIOD_H4,  "4h",    50);
   //--- EUR/USD: D1 for Daily DOL (Rules 3.1a/3.1b)
   PushCandles("EURUSD", PERIOD_D1,  "1day",  30);
   //--- GBP/USD: H1 for SMT divergence context
   PushCandles("GBPUSD", PERIOD_H1,  "1h",    50);
}

//+------------------------------------------------------------------+
//| Fetch candles for one symbol+timeframe and POST to backend       |
//| Implements the candle push format expected by signal-engine      |
//+------------------------------------------------------------------+
void PushCandles(string symbol, ENUM_TIMEFRAMES period, string tfId, int count)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, false);  // oldest-first order (index 0 = oldest)

   int copied = CopyRates(symbol, period, 0, count, rates);
   if(copied <= 0)
   {
      Print("ATLAS push FAILED | CopyRates error=", GetLastError(),
            " symbol=", symbol, " tf=", tfId);
      return;
   }

   //--- Build JSON body
   //    Format matches signal-engine candle ingestion schema:
   //    {"symbol":"EURUSD","timeframe":"5min","candles":[{...},...]}
   string body = "{";
   body += "\"symbol\":\"" + symbol + "\",";
   body += "\"timeframe\":\"" + tfId + "\",";
   body += "\"candles\":[";

   for(int i = 0; i < copied; i++)
   {
      //--- Convert MT5 datetime to ISO-8601: "YYYY.MM.DD HH:MM:SS" → "YYYY-MM-DDTHH:MM:SS"
      string dt = TimeToString(rates[i].time, TIME_DATE | TIME_SECONDS);
      StringReplace(dt, ".", "-");   // "YYYY-MM-DD HH:MM:SS"
      StringReplace(dt, " ", "T");   // "YYYY-MM-DDTHH:MM:SS"

      body += "{";
      body += "\"datetime\":\"" + dt + "\",";
      body += "\"open\":"    + DoubleToString(rates[i].open,   5) + ",";
      body += "\"high\":"    + DoubleToString(rates[i].high,   5) + ",";
      body += "\"low\":"     + DoubleToString(rates[i].low,    5) + ",";
      body += "\"close\":"   + DoubleToString(rates[i].close,  5) + ",";
      body += "\"volume\":"  + IntegerToString(rates[i].tick_volume);
      body += "}";
      if(i < copied - 1) body += ",";
   }

   body += "]}";

   int httpCode = HttpPost(CANDLE_URL, body);
   Print("ATLAS push: ", symbol, " ", tfId, " ", copied,
         " candles | HTTP ", httpCode);
}

//+------------------------------------------------------------------+
//| HTTP POST helper                                                  |
//| Returns HTTP status code, or -1 on WebRequest failure            |
//+------------------------------------------------------------------+
int HttpPost(string url, string body)
{
   char   bodyBytes[];
   char   responseBytes[];
   string responseHeaders;

   //--- Convert string to byte array (exclude null terminator)
   int bodyLen = StringLen(body);
   StringToCharArray(body, bodyBytes, 0, bodyLen);

   int httpCode = WebRequest(
      "POST",
      url,
      "Content-Type: application/json\r\n",
      3000,          // timeout ms
      bodyBytes,
      responseBytes,
      responseHeaders
   );

   if(httpCode == -1)
   {
      Print("ATLAS HttpPost FAILED | url=", url,
            " error=", GetLastError(),
            " (confirm Docker running and URL whitelisted in Tools→Options→Expert Advisors)");
   }
   return(httpCode);
}

//+------------------------------------------------------------------+
//| HTTP GET helper                                                   |
//| Returns response body string, or "" on error or non-200         |
//+------------------------------------------------------------------+
string HttpGet(string url)
{
   char   post[];          // empty body for GET
   char   responseBytes[];
   string responseHeaders;

   int httpCode = WebRequest(
      "GET",
      url,
      "",
      2000,          // timeout ms — tight for 1-second polling loop
      post,
      responseBytes,
      responseHeaders
   );

   if(httpCode == -1)
   {
      Print("ATLAS HttpGet FAILED | url=", url,
            " error=", GetLastError());
      return("");
   }

   if(httpCode != 200)
   {
      //--- Non-200 is not logged at Print level to avoid log spam during normal operation
      //    (backend returns 404 when no signal pending)
      return("");
   }

   return(CharArrayToString(responseBytes));
}

//+------------------------------------------------------------------+
//| POST acknowledgement to backend after trade or manage event      |
//| type:    "OPEN_ACK" or "MANAGE_ACK"                             |
//| status:  "OK", "ERROR", "PARTIAL_CLOSE_OK", etc.                |
//+------------------------------------------------------------------+
void PostAck(string type,
             string tradeId,
             ulong  ticket,
             string status,
             double price,
             int    errCode,
             string msg)
{
   string body = "{";
   body += "\"type\":\""     + type                              + "\",";
   body += "\"trade_id\":\"" + tradeId                          + "\",";
   body += "\"ticket\":"     + IntegerToString((long)ticket)    + ",";
   body += "\"status\":\""   + status                           + "\",";
   body += "\"price\":"      + DoubleToString(price, 5)         + ",";
   body += "\"error_code\":" + IntegerToString(errCode)         + ",";
   body += "\"message\":\""  + msg                              + "\"";
   body += "}";

   HttpPost(ACK_URL, body);
}