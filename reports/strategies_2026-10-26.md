# RMSE_BOT Strategy Lab — 2026-10-26
_Bot-generated strategies ranked by ROBUST profit (return x window-consistency), NOT win rate. Top = CANDIDATE; forward-test before promoting._

## XAUUSD  (25850 bars, 48 strategies tested)
 #    score  return$    PF   win  maxDD$ consist  rule (dir, entry, exit)
 1  49464.74 65952.99  1.66   38% 19484.04     75%  buy [high_vol & strong_trend & vol_quiet] rr1.5/be1.0
 2  42788.86 57051.81  1.32   56% 36307.02     75%  buy [high_vol & strong_trend & vol_quiet] rr1.5/be0.0
 3  35116.19 46821.59  1.62   48% 12189.81     75%  buy [high_vol & strong_trend & vol_quiet] rr1.0/be1.0
 4  26701.64 35602.19  1.60   59% 8557.42     75%  buy [high_vol & strong_trend & vol_quiet] rr0.75/be1.0
 5  26218.52 34958.03  1.46   69% 13157.02     75%  buy [high_vol & strong_trend & vol_quiet] rr0.75/be0.0
 6  25203.11 33604.15  1.27   54% 23590.17     75%  buy [trend_up & strong_trend & vol_quiet] rr1.5/be0.0
 7  24364.46 32485.94  1.35   61% 15210.84     75%  buy [high_vol & strong_trend & vol_quiet] rr1.0/be0.0
 8  22925.37 22925.37  1.31   62% 15063.56    100%  buy [trend_up & strong_trend & vol_quiet] rr1.0/be0.0
 9  17097.57 22796.76  1.40   36% 16830.38     75%  buy [trend_up & strong_trend & vol_quiet] rr1.5/be1.0
10  12442.16 16589.55  1.35   47% 10371.81     75%  buy [trend_up & strong_trend & vol_quiet] rr1.0/be1.0
11  8704.58 11606.11  1.26   66% 8426.90     75%  buy [trend_up & strong_trend & vol_quiet] rr0.75/be0.0
12  3778.33  5037.77  1.18   52% 6953.71     75%  buy [trend_up & strong_trend & vol_quiet] rr0.75/be1.0

## SOLUSDT  (2400 bars, 6 strategies tested)
 #    score  return$    PF   win  maxDD$ consist  rule (dir, entry, exit)
 1  4635.08  4635.08  1.59   47% 1935.06    100%  sell [ema_fast_above & rsi_bull & vol_rising] rr1.0/be1.0
 2  3924.92  3924.92  1.48   32% 2614.77    100%  sell [ema_fast_above & rsi_bull & vol_rising] rr1.5/be1.0
 3  1082.52  2165.04  1.32   51% 1660.49     50%  sell [ema_fast_above & rsi_bull & vol_rising] rr0.75/be1.0
 4   792.25  1056.34  1.10   55% 2698.76     75%  sell [ema_fast_above & rsi_bull & vol_rising] rr1.0/be0.0
 5   502.06  1004.12  1.12   62% 2302.26     50%  sell [ema_fast_above & rsi_bull & vol_rising] rr0.75/be0.0
 6   -92.69  -185.37  0.98   45% 3227.05     50%  sell [ema_fast_above & rsi_bull & vol_rising] rr1.5/be0.0
