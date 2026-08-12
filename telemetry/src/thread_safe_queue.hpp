// thread_safe_queue.hpp - bounded FIFO shared by the sensor and publisher threads.
//
// push() never blocks: if the queue is full (for example while the MQTT broker
// is down) the oldest item is dropped so memory stays bounded and the newest
// readings survive. pop() blocks until an item arrives or close() is called.
#pragma once

#include <condition_variable>
#include <cstddef>
#include <deque>
#include <mutex>
#include <optional>

template <typename T>
class ThreadSafeQueue {
public:
    explicit ThreadSafeQueue(std::size_t max_size) : max_size_(max_size) {}

    // Add an item. Ignored after close().
    void push(T item) {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (closed_) {
                return;
            }
            if (items_.size() >= max_size_) {
                items_.pop_front();
                ++dropped_;
            }
            items_.push_back(std::move(item));
        }
        cv_.notify_one();
    }

    // Wait for the next item. Returns std::nullopt once closed and empty.
    std::optional<T> pop() {
        std::unique_lock<std::mutex> lock(mutex_);
        cv_.wait(lock, [this] { return !items_.empty() || closed_; });
        if (items_.empty()) {
            return std::nullopt;
        }
        T item = std::move(items_.front());
        items_.pop_front();
        return item;
    }

    // Wake every waiting pop(). Items already queued can still be popped.
    void close() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            closed_ = true;
        }
        cv_.notify_all();
    }

    std::size_t size() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return items_.size();
    }

    // Number of items discarded because the queue was full.
    std::size_t dropped() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return dropped_;
    }

private:
    const std::size_t max_size_;
    mutable std::mutex mutex_;
    std::condition_variable cv_;
    std::deque<T> items_;
    std::size_t dropped_ = 0;
    bool closed_ = false;
};
