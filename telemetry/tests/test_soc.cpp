#include <gtest/gtest.h>

#include "soc_estimator.hpp"

TEST(SocEstimator, StartsAtInitialSoc) {
    SocEstimator soc(2000.0, 80.0);
    EXPECT_DOUBLE_EQ(soc.soc_pct(), 80.0);
    EXPECT_DOUBLE_EQ(soc.remaining_mah(), 1600.0);
}

TEST(SocEstimator, OneAmpForOneHourOnTwoAmpHours) {
    SocEstimator soc(2000.0, 100.0);
    // 3600 one-second samples at 1000 mA = 1000 mAh used
    for (int i = 0; i < 3600; ++i) {
        soc.update(1000.0, 1.0);
    }
    EXPECT_NEAR(soc.soc_pct(), 50.0, 1e-9);
}

TEST(SocEstimator, TenHertzSamplesMatchOneBigStep) {
    SocEstimator small_steps(2500.0, 100.0);
    SocEstimator one_step(2500.0, 100.0);
    for (int i = 0; i < 600; ++i) {  // 60 s at 10 Hz
        small_steps.update(400.0, 0.1);
    }
    one_step.update(400.0, 60.0);
    EXPECT_NEAR(small_steps.soc_pct(), one_step.soc_pct(), 1e-9);
}

TEST(SocEstimator, ClampsAtEmpty) {
    SocEstimator soc(100.0, 10.0);
    soc.update(1000.0, 3600.0);  // far more than is left
    EXPECT_DOUBLE_EQ(soc.soc_pct(), 0.0);
}

TEST(SocEstimator, NegativeCurrentChargesAndClampsAtFull) {
    SocEstimator soc(1000.0, 50.0);
    soc.update(-500.0, 3600.0);  // +500 mAh
    EXPECT_NEAR(soc.soc_pct(), 100.0, 1e-9);
    soc.update(-500.0, 3600.0);
    EXPECT_DOUBLE_EQ(soc.soc_pct(), 100.0);
}

TEST(SocEstimator, IgnoresNonPositiveTimeStep) {
    SocEstimator soc(1000.0, 50.0);
    soc.update(500.0, 0.0);
    soc.update(500.0, -1.0);
    EXPECT_DOUBLE_EQ(soc.soc_pct(), 50.0);
}

TEST(SocEstimator, ClampsInitialSoc) {
    EXPECT_DOUBLE_EQ(SocEstimator(1000.0, 150.0).soc_pct(), 100.0);
    EXPECT_DOUBLE_EQ(SocEstimator(1000.0, -5.0).soc_pct(), 0.0);
}
