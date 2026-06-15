# RMSE_BOT Strategy Lab — 2026-06-15
_Bot-generated strategies ranked by ROBUST profit (return x window-consistency), NOT win rate. Top = CANDIDATE; forward-test before promoting._

## XAUUSD  (57032 bars, 48 strategies tested)
 #    score  return$    PF   win  maxDD$ consist  rule (dir, entry, exit)
 1   177.96   177.96  2.01   61%   25.37    100%  buy [rsi_overbought & high_vol & session_asia] rr1.5/be0.0
 2   177.60   177.60  2.62   43%   17.83    100%  buy [rsi_overbought & high_vol & session_asia] rr1.5/be1.0
 3   174.12   174.12  1.16   48%  100.67    100%  buy [ema_fast_above & rsi_bear & session_london] rr1.5/be0.0
 4   109.57   109.57  2.15   52%   16.22    100%  buy [rsi_overbought & high_vol & session_asia] rr1.0/be1.0
 5    97.56   130.08  1.18   57%   88.17     75%  buy [ema_fast_above & rsi_bear & session_london] rr1.0/be0.0
 6    71.33    95.11  1.71   65%   20.59     75%  buy [rsi_overbought & high_vol & session_asia] rr1.0/be0.0
 7    60.26    80.35  1.22   42%   37.87     75%  buy [trend_up & rsi_overbought & high_vol] rr1.0/be1.0
 8    58.23    77.64  1.91   60%   14.23     75%  buy [rsi_overbought & high_vol & session_asia] rr0.75/be1.0
 9    56.19    74.92  1.21   42%   40.18     75%  buy [rsi_overbought & high_vol] rr1.0/be1.0
10    56.19    74.92  1.21   42%   40.18     75%  buy [ema_fast_above & rsi_overbought & high_vol] rr1.0/be1.0
11    54.33    72.44  1.11   30%   50.84     75%  buy [rsi_overbought] rr1.5/be1.0
12    43.23    86.47  1.25   31%   39.69     50%  buy [trend_up & rsi_overbought & high_vol] rr1.5/be1.0
