#include "soc_estimator.hpp"

#include <algorithm>

SocEstimator::SocEstimator(double capacity_mah, double initial_soc_pct)
    : capacity_mah_(capacity_mah > 0.0 ? capacity_mah : 1.0) {
    double soc = std::clamp(initial_soc_pct, 0.0, 100.0);
    remaining_mah_ = capacity_mah_ * soc / 100.0;
}

double SocEstimator::update(double current_ma, double dt_s) {
    if (dt_s > 0.0) {
        double used_mah = current_ma * dt_s / 3600.0;
        remaining_mah_ = std::clamp(remaining_mah_ - used_mah, 0.0, capacity_mah_);
    }
    return soc_pct();
}

double SocEstimator::soc_pct() const {
    return remaining_mah_ / capacity_mah_ * 100.0;
}
