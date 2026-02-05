from dataclasses import dataclass
from typing import Tuple
from math import isfinite
from scipy.stats import beta as beta_dist

# Priors (podemos ajustar depois)
# FT: média liga ~0.75, prior size m = 40 (jogos "virtuais")
A_FT = 30
B_FT = 10  # média = 30/(30+10)=0.75

# HT: média liga ~0.80, prior size m = 40
A_HT = 32
B_HT = 8   # 32/(32+8)=0.80

CONF_LEVEL = 0.05  # quantil inferior 5%

@dataclass
class BetaPosterior:
    a: float
    b: float

    @property
    def mean(self) -> float:
        return self.a / (self.a + self.b) if (self.a + self.b) > 0 else 0.0

    def quantile_lower(self, alpha: float = CONF_LEVEL) -> float:
        try:
            q = beta_dist.ppf(alpha, self.a, self.b)
            return float(q) if isfinite(q) else 0.0
        except Exception:
            return 0.0

def beta_posterior_from_counts(s: int, n: int, a0: int, b0: int) -> BetaPosterior:
    return BetaPosterior(a=a0 + s, b=b0 + n - s)

def combine_two_probs(p1: float, p2: float) -> float:
    return (p1 + p2) / 2.0

def compute_game_probs(teamA_stats: dict, teamB_stats: dict) -> dict:
    # HT
    postA_ht = beta_posterior_from_counts(
        s=teamA_stats["over_05_ht_s"],
        n=teamA_stats["over_05_ht_n"],
        a0=A_HT,
        b0=B_HT,
    )
    postB_ht = beta_posterior_from_counts(
        s=teamB_stats["over_05_ht_s"],
        n=teamB_stats["over_05_ht_n"],
        a0=A_HT,
        b0=B_HT,
    )

    p_ht_mean = combine_two_probs(postA_ht.mean, postB_ht.mean)
    p_ht_min  = combine_two_probs(
        postA_ht.quantile_lower(CONF_LEVEL),
        postB_ht.quantile_lower(CONF_LEVEL),
    )

    # FT
    postA_ft = beta_posterior_from_counts(
        s=teamA_stats["over_15_ft_s"],
        n=teamA_stats["over_15_ft_n"],
        a0=A_FT,
        b0=B_FT,
    )
    postB_ft = beta_posterior_from_counts(
        s=teamB_stats["over_15_ft_s"],
        n=teamB_stats["over_15_ft_n"],
        a0=A_FT,
        b0=B_FT,
    )

    p_ft_mean = combine_two_probs(postA_ft.mean, postB_ft.mean)
    p_ft_min  = combine_two_probs(
        postA_ft.quantile_lower(CONF_LEVEL),
        postB_ft.quantile_lower(CONF_LEVEL),
    )

    return {
        "over05_ht": {
            "p_mean": p_ht_mean,
            "p_min": p_ht_min,
        },
        "over15_ft": {
            "p_mean": p_ft_mean,
            "p_min": p_ft_min,
        },
        "posteriors": {
            "A_ht": postA_ht,
            "B_ht": postB_ht,
            "A_ft": postA_ft,
            "B_ft": postB_ft,
        }
    }
