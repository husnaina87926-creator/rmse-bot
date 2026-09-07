# RMSE_BOT Strategy Lab — 2026-09-07
_Bot-generated strategies ranked by ROBUST profit (return x window-consistency), NOT win rate. Top = CANDIDATE; forward-test before promoting._

## XAUUSD  (25848 bars, 42 strategies tested)
 #    score  return$    PF   win  maxDD$ consist  rule (dir, entry, exit)
 1  51286.35 68381.80  1.59   34% 16112.98     75%  buy [high_vol & vol_quiet] rr1.5/be1.0
 2  32529.16 43372.22  1.57   43% 7216.64     75%  buy [high_vol & vol_quiet] rr1.0/be1.0
 3  18970.98 25294.64  1.60   44% 6522.17     75%  buy [high_vol & strong_trend & vol_quiet] rr1.0/be1.0
 4  18654.20 24872.27  1.57   33% 10278.34     75%  buy [high_vol & strong_trend & vol_quiet] rr1.5/be1.0
 5  14808.49 19744.65  1.40   51% 5189.76     75%  buy [high_vol & vol_quiet] rr0.75/be1.0
 6  12089.18 16118.91  1.51   53% 5248.13     75%  buy [high_vol & strong_trend & vol_quiet] rr0.75/be1.0
 7  10849.01 14465.35  1.21   55% 6879.00     75%  buy [high_vol & vol_quiet] rr1.0/be0.0
 8  10182.05 20364.10  1.17   49% 19331.50     50%  buy [high_vol & vol_quiet] rr1.5/be0.0
 9  9049.97 12066.63  1.25   57% 8312.63     75%  buy [high_vol & strong_trend & vol_quiet] rr1.0/be0.0
10  8180.56 10907.42  1.19   50% 12476.62     75%  buy [high_vol & strong_trend & vol_quiet] rr1.5/be0.0
11  8122.54 10830.05  1.20   53% 9694.63     75%  buy [trend_up & rsi_bear & session_london] rr0.75/be1.0
12  6993.28  9324.38  1.18   61% 7378.47     75%  buy [high_vol & vol_quiet] rr0.75/be0.0

## SOLUSDT  (2400 bars, 6 strategies tested)
 #    score  return$    PF   win  maxDD$ consist  rule (dir, entry, exit)
 1    -0.00 -2411.44  0.52   36% 2686.39      0%  sell [trend_down & high_vol] rr0.75/be1.0
 2  -241.36  -482.72  0.96   50% 5064.94     50%  sell [trend_down & high_vol] rr1.5/be0.0
 3  -521.22 -2084.87  0.72   53% 2621.80     25%  sell [trend_down & high_vol] rr0.75/be0.0
 4  -550.60 -1101.19  0.87   53% 3033.85     50%  sell [trend_down & high_vol] rr1.0/be0.0
 5  -608.57 -2434.26  0.52   28% 2595.20     25%  sell [trend_down & high_vol] rr1.0/be1.0
 6  -624.29 -2497.16  0.51   22% 2752.10     25%  sell [trend_down & high_vol] rr1.5/be1.0
