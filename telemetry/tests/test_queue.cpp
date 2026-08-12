#include <gtest/gtest.h>

#include <thread>
#include <vector>

#include "thread_safe_queue.hpp"

TEST(ThreadSafeQueue, FifoOrder) {
    ThreadSafeQueue<int> q(10);
    q.push(1);
    q.push(2);
    q.push(3);
    EXPECT_EQ(q.size(), 3u);
    EXPECT_EQ(*q.pop(), 1);
    EXPECT_EQ(*q.pop(), 2);
    EXPECT_EQ(*q.pop(), 3);
}

TEST(ThreadSafeQueue, DropsOldestWhenFull) {
    ThreadSafeQueue<int> q(3);
    for (int i = 1; i <= 5; ++i) {
        q.push(i);
    }
    EXPECT_EQ(q.size(), 3u);
    EXPECT_EQ(q.dropped(), 2u);
    EXPECT_EQ(*q.pop(), 3);  // 1 and 2 were dropped
}

TEST(ThreadSafeQueue, CloseDrainsThenReturnsEmpty) {
    ThreadSafeQueue<int> q(10);
    q.push(7);
    q.close();
    q.push(8);  // ignored after close
    EXPECT_EQ(*q.pop(), 7);
    EXPECT_FALSE(q.pop().has_value());
}

TEST(ThreadSafeQueue, CloseWakesBlockedConsumer) {
    ThreadSafeQueue<int> q(10);
    bool got_nullopt = false;
    std::thread consumer([&] { got_nullopt = !q.pop().has_value(); });
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    q.close();
    consumer.join();
    EXPECT_TRUE(got_nullopt);
}

TEST(ThreadSafeQueue, ProducerConsumerDeliversEverything) {
    constexpr int kCount = 20000;
    ThreadSafeQueue<int> q(kCount);  // big enough that nothing is dropped
    std::vector<int> received;
    received.reserve(kCount);

    std::thread consumer([&] {
        while (auto v = q.pop()) {
            received.push_back(*v);
        }
    });
    std::thread producer([&] {
        for (int i = 0; i < kCount; ++i) {
            q.push(i);
        }
        q.close();
    });
    producer.join();
    consumer.join();

    ASSERT_EQ(received.size(), static_cast<size_t>(kCount));
    for (int i = 0; i < kCount; ++i) {
        ASSERT_EQ(received[i], i);  // order preserved
    }
}
