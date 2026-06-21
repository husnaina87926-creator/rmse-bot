# RMSE_BOT Strategy Lab — 2026-06-21
_Bot-generated strategies ranked by ROBUST profit (return x window-consistency), NOT win rate. Top = CANDIDATE; forward-test before promoting._

## XAUUSD  (25827 bars, 48 strategies tested)
 #    score  return$    PF   win  maxDD$ consist  rule (dir, entry, exit)
 1  14730.82 14730.82  1.33   46% 4413.98    100%  buy [trend_up & rsi_overbought & high_vol] rr1.0/be1.0
 2  13933.91 18578.54  1.41   35% 6599.55     75%  buy [trend_up & rsi_overbought & high_vol] rr1.5/be1.0
 3  8838.26 11784.35  1.17   49% 10926.68     75%  sell [trend_up & ema_fast_below & session_ny] rr1.5/be0.0
 4  8636.61 11515.48  1.37   34% 4118.35     75%  buy [rsi_overbought & high_vol & strong_trend] rr1.5/be1.0
 5  7528.00 10037.33  1.20   50% 8011.02     75%  sell [low_vol & session_asia & sweep_up] rr1.5/be0.0
 6  7064.08  9418.78  1.22   64% 5358.96     75%  sell [low_vol & session_asia & sweep_up] rr0.75/be0.0
 7  6658.88  6658.88  1.11   31% 7802.11    100%  buy [rsi_overbought] rr1.5/be1.0
 8  6162.07  8216.09  1.22   51% 4708.12     75%  buy [rsi_overbought & high_vol & strong_trend] rr1.5/be0.0
 9  5925.52  7900.69  1.16   56% 8614.86     75%  sell [low_vol & session_asia & sweep_up] rr1.0/be0.0
10  5268.95  7025.26  1.21   42% 5701.79     75%  buy [rsi_overbought & high_vol & strong_trend] rr1.0/be1.0
11  4680.26  6240.35  1.14   63% 8781.96     75%  sell [trend_up & ema_fast_below & session_ny] rr0.75/be0.0
12  3506.01  4674.68  1.15   54% 4785.38     75%  sell [low_vol & session_asia & sweep_up] rr0.75/be1.0
