// soc_estimator.hpp - state of charge by coulomb counting.
//
//   remaining_mAh -= current_mA * dt_hours
//   SoC %         = remaining_mAh / capacity_mAh * 100
//
// Positive current means the battery is discharging into the load (current
// flows VIN+ -> VIN- through the INA219). Negative current charges it.
// Coulomb counting drifts over time; restart with --initial-soc after a full
// charge to re-anchor it.
#pragma once

class SocEstimator {
public:
    SocEstimator(double capacity_mah, double initial_soc_pct);

    // Integrate one sample. dt_s is the time since the previous sample.
    // Returns the new SoC in percent, clamped to [0, 100].
    double update(double current_ma, double dt_s);

    double soc_pct() const;
    double remaining_mah() const { return remaining_mah_; }
    double capacity_mah() const { return capacity_mah_; }

private:
    double capacity_mah_;
    double remaining_mah_;
};
