// FTMO_Bridge.mq5
#property copyright "TradingView Bridge"
#property link      "https://tradingview-webhook.karloestrada.workers.dev"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

CTrade trade;
string processedSignals[100]; // Track last 100 processed signal IDs
int processedCount = 0;

input string  ServerURL   = "https://tradingview-webhook.karloestrada.workers.dev"; // no trailing slash
input string  AccountKey  = "FTMO";
input double  MaxRiskPct  = 0.5;   // guardrail (should match TradingView)
input int     PollMs      = 1000;

// Lot Size Settings
input bool    UseFixedLot = false;  // Use fixed lot size instead of calculation
input double  FixedLotSize = 0.01;  // Fixed lot size to use
input bool    UseEquityPercent = true;  // Use % of equity for position sizing
input double  EquityPercent = 1.0;  // % of equity per trade (e.g., 1.0 = 1%)
input double  MaxLotSize = 0.10;    // Maximum allowed lot size
input double  MinLotSize = 0.01;    // Minimum lot size

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   // Set timer for polling
   EventSetTimer(MathMax(1, PollMs/1000));
   
   // Initialize trade class
   trade.SetExpertMagicNumber(123456);
   trade.SetDeviationInPoints(30);
   
   Print("FTMO Bridge EA started");
   Print("Server: ", ServerURL);
   Print("Account: ", AccountKey);
   
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("FTMO Bridge EA stopped");
}

//+------------------------------------------------------------------+
//| Timer function                                                   |
//+------------------------------------------------------------------+
void OnTimer()
{
   CheckQueue();
}

//+------------------------------------------------------------------+
//| Check queue for new signals                                      |
//+------------------------------------------------------------------+
void CheckQueue()
{
   string url = ServerURL + "/dequeue?account=" + AccountKey;
   string headers;
   char post[], result[];
   string result_headers;
   int timeout = 5000;
   
   // Prepare empty POST data
   ArrayResize(post, 0);
   
   // Make the request
   int res = WebRequest("GET", url, NULL, NULL, timeout, post, 0, result, result_headers);
   
   // Check for errors
   if(res == -1)
   {
      int error = GetLastError();
      if(error != 5203) // 5203 = no data, which is normal
         Print("WebRequest error: ", error);
      return;
   }
   
   // Convert result to string
   string result_str = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   
   // Check if empty or null
   if(result_str == "" || result_str == "null" || StringLen(result_str) < 10)
      return;
   
   Print("Received signal: ", result_str);
   
   // Parse JSON
   string signalId = JsonGet(result_str, "signalId");
   string event = JsonGet(result_str, "event");
   string symbol = MapSymbol(JsonGet(result_str, "symbol"));
   string side = JsonGet(result_str, "side");
   double sl = StringToDouble(JsonGet(result_str, "sl"));
   double qtyusd = StringToDouble(JsonGet(result_str, "qty_usd"));
   int magic = (int)StringToInteger(JsonGet(result_str, "magic"));
   
   // Check if signal already processed
   if(IsSignalProcessed(signalId))
   {
      Print("Duplicate signal ignored: ", signalId);
      return;
   }
   
   // Add to processed signals
   AddProcessedSignal(signalId);
   
   // Set magic number for this trade
   if(magic > 0)
      trade.SetExpertMagicNumber(magic);
   
   Print("Processing new signal: ", signalId, " - ", event, " ", symbol, " ", side);
   
   // Process the signal
   if(event == "entry")
   {
      ProcessEntrySignal(symbol, side, sl, qtyusd);
   }
   else if(event == "exit")
   {
      ProcessExitSignal(symbol, side);
   }
}

//+------------------------------------------------------------------+
//| Process entry signal                                             |
//+------------------------------------------------------------------+
void ProcessEntrySignal(string symbol, string side, double sl, double qtyusd)
{
   // Check if symbol exists
   if(!SymbolSelect(symbol, true))
   {
      Print("Symbol not found: ", symbol);
      return;
   }
   
   // Get current price
   double price;
   if(side == "BUY")
      price = SymbolInfoDouble(symbol, SYMBOL_ASK);
   else if(side == "SELL")
      price = SymbolInfoDouble(symbol, SYMBOL_BID);
   else
   {
      Print("Invalid side: ", side);
      return;
   }
   
   // Calculate lot size based on risk
   double lot = CalculateLotSize(symbol, price, sl, qtyusd);
   if(lot <= 0)
   {
      Print("Invalid lot size calculated");
      return;
   }
   
   // Execute trade
   bool success = false;
   
   if(side == "BUY")
   {
      success = trade.Buy(lot, symbol, price, sl, 0, "TV-Bridge");
   }
   else if(side == "SELL")
   {
      success = trade.Sell(lot, symbol, price, sl, 0, "TV-Bridge");
   }
   
   if(success)
   {
      Print("Trade executed: ", side, " ", lot, " ", symbol, " @ ", price, " SL: ", sl);
   }
   else
   {
      Print("Trade failed: ", trade.ResultRetcode(), " - ", trade.ResultComment());
   }
}

//+------------------------------------------------------------------+
//| Process exit signal                                              |
//+------------------------------------------------------------------+
void ProcessExitSignal(string symbol, string side)
{
   // Determine position type to close
   ENUM_POSITION_TYPE pos_type;
   if(side == "BUY")
      pos_type = POSITION_TYPE_SELL;  // Close sells
   else if(side == "SELL")
      pos_type = POSITION_TYPE_BUY;   // Close buys
   else
   {
      Print("Invalid side for exit: ", side);
      return;
   }
   
   ClosePositions(symbol, pos_type);
}

//+------------------------------------------------------------------+
//| Calculate lot size based on risk                                 |
//+------------------------------------------------------------------+
double CalculateLotSize(string symbol, double price, double sl, double risk_usd)
{
   double lot = 0.01;
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   
   // Option 1: Use Fixed Lot Size
   if(UseFixedLot)
   {
      lot = FixedLotSize;
      Print("Using fixed lot size: ", lot);
   }
   // Option 2: Use % of Equity
   else if(UseEquityPercent)
   {
      double equity_risk = equity * (EquityPercent / 100.0);
      double stop_distance = MathAbs(price - sl);
      
      if(stop_distance > 0 && price > 0)
      {
         // Calculate lot size based on equity risk
         // For crypto: equity_risk / (stop_distance * contract_size * price)
         // Simplified: equity_risk / (stop_distance * price) for 1 unit contracts
         double contract_value = price; // 1 lot = 1 unit of base currency
         lot = equity_risk / (stop_distance * contract_value);
         
         Print("Equity: $", equity, ", Risk: ", EquityPercent, "% = $", equity_risk);
         Print("Stop distance: ", stop_distance, ", Price: ", price, ", Calculated lot: ", lot);
      }
      else
      {
         // Fallback: use simple equity percentage for position size
         lot = equity_risk / (price * 1000); // Rough approximation
         Print("Using fallback calculation - Equity risk: $", equity_risk, ", Lot: ", lot);
      }
   }
   // Option 3: Use TradingView risk amount
   else
   {
      if(risk_usd <= 0)
         risk_usd = equity * (MaxRiskPct / 100.0);
      
      double stop_distance = MathAbs(price - sl);
      if(stop_distance <= 0)
      {
         Print("Invalid stop distance: ", stop_distance, " - using minimum lot");
         lot = MinLotSize;
      }
      else
      {
         // Conservative risk-based calculation
         if(risk_usd > 1000)
            lot = 0.10;
         else if(risk_usd > 500)
            lot = 0.05;
         else if(risk_usd > 100)
            lot = 0.02;
         else
            lot = 0.01;
         
         Print("Risk USD: ", risk_usd, ", Stop distance: ", stop_distance, ", Calculated lot: ", lot);
      }
   }
   
   // Apply EA constraints
   lot = MathMax(MinLotSize, MathMin(lot, MaxLotSize));
   
   // Get symbol constraints
   double min_lot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double max_lot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double lot_step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   
   // Apply symbol constraints
   lot = MathMax(min_lot, MathMin(lot, max_lot));
   lot = MathRound(lot / lot_step) * lot_step;
   
   Print("Final lot size: ", lot, " (Min: ", MinLotSize, ", Max: ", MaxLotSize, ")");
   
   return NormalizeDouble(lot, 2);
}

//+------------------------------------------------------------------+
//| Close positions for symbol                                       |
//+------------------------------------------------------------------+
void ClosePositions(string symbol, ENUM_POSITION_TYPE pos_type)
{
   int closed = 0;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
      {
         if(PositionSelectByTicket(ticket))
         {
            if(PositionGetString(POSITION_SYMBOL) == symbol && 
               PositionGetInteger(POSITION_TYPE) == pos_type)
            {
               if(trade.PositionClose(ticket))
               {
                  closed++;
                  Print("Closed position: ", ticket);
               }
            }
         }
      }
   }
   
   if(closed > 0)
      Print("Closed ", closed, " positions for ", symbol);
}

//+------------------------------------------------------------------+
//| Simple JSON parser                                               |
//+------------------------------------------------------------------+
string JsonGet(string json, string key)
{
   string search = "\"" + key + "\":";
   int start = StringFind(json, search);
   if(start < 0)
      return "";
   
   start += StringLen(search);
   
   // Skip whitespace
   while(start < StringLen(json) && 
         (StringGetCharacter(json, start) == ' ' || 
          StringGetCharacter(json, start) == '\t'))
      start++;
   
   // Check if value is string (quoted)
   bool is_string = (StringGetCharacter(json, start) == '"');
   if(is_string)
      start++; // Skip opening quote
   
   // Find end of value
   int end = start;
   if(is_string)
   {
      // Find closing quote
      while(end < StringLen(json) && StringGetCharacter(json, end) != '"')
         end++;
   }
   else
   {
      // Find comma or closing brace
      while(end < StringLen(json) && 
            StringGetCharacter(json, end) != ',' && 
            StringGetCharacter(json, end) != '}')
         end++;
   }
   
   // Extract value
   string value = StringSubstr(json, start, end - start);
   
   // Clean up value
   StringReplace(value, "\"", "");
   StringTrimLeft(value);
   StringTrimRight(value);
   
   if(value == "null")
      value = "0";
   
   return value;
}

//+------------------------------------------------------------------+
//| Map TradingView symbol to broker symbol                          |
//+------------------------------------------------------------------+
string MapSymbol(string tv_symbol)
{
   // Map TradingView symbols to FTMO/MT5 broker symbols
   
   // Crypto symbols - remove .P suffix
   if(tv_symbol == "XRPUSDT.P") return "XRPUSD";
   if(tv_symbol == "BTCUSDT.P") return "BTCUSD";
   if(tv_symbol == "ETHUSDT.P") return "ETHUSD";
   if(tv_symbol == "ADAUSDT.P") return "ADAUSD";
   if(tv_symbol == "SOLUSDT.P") return "SOLUSD";
   if(tv_symbol == "DOTUSDT.P") return "DOTUSD";
   if(tv_symbol == "LINKUSDT.P") return "LINKUSD";
   if(tv_symbol == "AVAXUSDT.P") return "AVAXUSD";
   
   // Remove any .P suffix for other symbols
   if(StringFind(tv_symbol, ".P") >= 0)
   {
      string clean_symbol = tv_symbol;
      StringReplace(clean_symbol, ".P", "");
      StringReplace(clean_symbol, "USDT", "USD");
      return clean_symbol;
   }
   
   // Forex pairs - add .a suffix if needed (uncomment if your broker uses this)
   // if(StringFind(tv_symbol, "USD") >= 0) return tv_symbol + ".a";
   
   // Metals and indices
   if(tv_symbol == "XAUUSD") return "GOLD";
   if(tv_symbol == "XAGUSD") return "SILVER";
   if(tv_symbol == "US30") return "DJ30";
   if(tv_symbol == "SPX500") return "SP500";
   if(tv_symbol == "NAS100") return "NAS100";
   
   return tv_symbol;
}

//+------------------------------------------------------------------+
//| Check if signal ID was already processed                         |
//+------------------------------------------------------------------+
bool IsSignalProcessed(string signalId)
{
   if(signalId == "" || signalId == "0")
      return false; // Allow signals without ID (backward compatibility)
   
   for(int i = 0; i < processedCount && i < ArraySize(processedSignals); i++)
   {
      if(processedSignals[i] == signalId)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Add signal ID to processed list                                  |
//+------------------------------------------------------------------+
void AddProcessedSignal(string signalId)
{
   if(signalId == "" || signalId == "0")
      return;
   
   int index = processedCount % ArraySize(processedSignals);
   processedSignals[index] = signalId;
   processedCount++;
   
   Print("Signal added to processed list: ", signalId, " (", processedCount, " total)");
}