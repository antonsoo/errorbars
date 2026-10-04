# Third-party notices

## Inverse normal distribution

`web/src/normal.ts` adapts `_normal_dist_inv_cdf` from CPython 3.12.12,
[`Lib/statistics.py`](https://github.com/python/cpython/blob/v3.12.12/Lib/statistics.py).
It implements M. J. Wichura (1988), "Algorithm AS 241: The Percentage Points of
the Normal Distribution", Applied Statistics 37(3), 477-484.

Copyright (c) 2001-2023 Python Software Foundation. All rights reserved.
The full upstream license and notices are retained in
[`LICENSES/Python-2.0.txt`](LICENSES/Python-2.0.txt).

The adaptation is a TypeScript translation of the standard-normal case
(mean 0, standard deviation 1), adds finite-domain checks, and uses the lower
probability tail when converting confidence levels. No Python runtime code
is loaded by the web page.

## Fonts

Local font files and their license notices are under
[`web/src/fonts/`](web/src/fonts/).
