# RMSE_BOT Strategy Lab — 2026-09-28
_Bot-generated strategies ranked by ROBUST profit (return x window-consistency), NOT win rate. Top = CANDIDATE; forward-test before promoting._

## XAUUSD  (25842 bars, 48 strategies tested)
 #    score  return$    PF   win  maxDD$ consist  rule (dir, entry, exit)
 1  38667.63 38667.63  1.71   35% 11872.13    100%  buy [high_vol & strong_trend & vol_quiet] rr1.5/be1.0
 2  35565.15 35565.15  1.69   46% 7533.52    100%  buy [high_vol & strong_trend & vol_quiet] rr1.0/be1.0
 3  31163.06 41550.74  1.22   55% 11274.19     75%  sell [ema_fast_below & rsi_bear & vol_rising] rr1.0/be0.0
 4  23967.07 23967.07  1.62   56% 6061.92    100%  buy [high_vol & strong_trend & vol_quiet] rr0.75/be1.0
 5  21529.86 28706.48  1.30   29% 9337.15     75%  sell [trend_down & rsi_bear & vol_rising] rr1.5/be1.0
 6  19903.73 19903.73  1.31   59% 10634.31    100%  buy [high_vol & strong_trend & vol_quiet] rr1.0/be0.0
 7  15255.60 20340.80  1.26   52% 15961.28     75%  buy [high_vol & strong_trend & vol_quiet] rr1.5/be0.0
 8  14143.88 18858.51  1.41   66% 8227.88     75%  buy [high_vol & strong_trend & vol_quiet] rr0.75/be0.0
 9  14139.03 28278.05  1.55   29% 4455.69     50%  sell [ema_fast_below & rsi_bear & vol_rising] rr1.5/be1.0
10  13778.93 27557.86  1.29   47% 12103.13     50%  sell [ema_fast_below & rsi_bear & vol_rising] rr1.5/be0.0
11  10305.89 13741.18  1.22   39% 3868.14     75%  sell [ema_fast_below & rsi_bear & vol_rising] rr1.0/be1.0
12  7609.70 15219.40  1.14   61% 5081.25     50%  sell [ema_fast_below & rsi_bear & vol_rising] rr0.75/be0.0

## SOLUSDT  (2400 bars, 6 strategies tested)
 #    score  return$    PF   win  maxDD$ consist  rule (dir, entry, exit)
 1    -0.00 -2119.40  0.58   38% 2425.37      0%  sell [trend_down & high_vol] rr0.75/be1.0
 2    -0.00 -2214.79  0.56   24% 2498.49      0%  sell [trend_down & high_vol] rr1.5/be1.0
 3  -258.04  -516.08  0.95   50% 5027.53     50%  sell [trend_down & high_vol] rr1.5/be0.0
 4  -494.85 -1979.40  0.72   53% 2629.71     25%  sell [trend_down & high_vol] rr0.75/be0.0
 5  -525.39 -1050.78  0.87   53% 3073.08     50%  sell [trend_down & high_vol] rr1.0/be0.0
 6  -536.20 -2144.80  0.58   29% 2323.89     25%  sell [trend_down & high_vol] rr1.0/be1.0
