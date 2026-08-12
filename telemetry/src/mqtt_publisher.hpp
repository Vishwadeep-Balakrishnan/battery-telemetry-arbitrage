// mqtt_publisher.hpp - thin wrapper around the libmosquitto C client.
//
// libmosquitto runs its own network thread (mosquitto_loop_start). That thread
// reconnects automatically with a backoff when the broker goes away, so this
// class only needs to track whether we are currently connected.
#pragma once

#include <atomic>
#include <string>

struct mosquitto;

class MqttPublisher {
public:
    MqttPublisher(std::string host, int port, std::string client_id);
    ~MqttPublisher();

    MqttPublisher(const MqttPublisher &) = delete;
    MqttPublisher &operator=(const MqttPublisher &) = delete;

    // Start the network thread and begin connecting. Returns false only on
    // setup errors; an unreachable broker is retried in the background.
    bool start();

    // Publish one message at QoS 0. Returns false if not connected.
    bool publish(const std::string &topic, const std::string &payload);

    bool connected() const { return connected_.load(); }

    // Disconnect and stop the network thread. Safe to call more than once.
    void stop();

private:
    static void on_connect(struct mosquitto *mosq, void *self, int rc);
    static void on_disconnect(struct mosquitto *mosq, void *self, int rc);

    std::string host_;
    int port_;
    std::string client_id_;
    struct mosquitto *mosq_ = nullptr;
    std::atomic<bool> connected_{false};
    bool running_ = false;
};
