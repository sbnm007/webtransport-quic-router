import pulsar
import time
import sys

#--- Configuration ---

PULSAR_BROKER_URL = 'pulsar://192.168.49.2:6650 '  #Replace with your Pulsar broker URL

print("--- Apache Pulsar High-Performance Consumer ---")
print(f"Connecting to Pulsar at: {PULSAR_BROKER_URL}")

client = None
consumer = None
##Replace <your-broker-pod-name> with the actual name from step 1
#kubectl exec -it broker -n pulsar -- \
#bin/pulsar-client consume persistent://public/default/video-topic -s "my-video-subscription" -n 0
try:
    if len(sys.argv) < 2: 
        print("Usage: python consumer.py <consumer_name>")
        sys.exit(1)

    consumer_name_arg = sys.argv[1]
    TOPIC_NAME = f"persistent://public/default/{consumer_name_arg}-topic"
    SUBSCRIPTION_NAME = f"my-{consumer_name_arg}-subscription"

    print(f"Using Topic: {TOPIC_NAME}")
    print(f"Using Subscription: {SUBSCRIPTION_NAME}\n")

    #--- Step 1: Create a Pulsar Client ---
    client = pulsar.Client(
        PULSAR_BROKER_URL,
        operation_timeout_seconds=30,
        use_tls=False
    )
    print("Pulsar Client created successfully.")

    #--- Step 2: Create a High-Performance Consumer ---
    consumer = client.subscribe(
        TOPIC_NAME,
        SUBSCRIPTION_NAME,
        consumer_type=pulsar.ConsumerType.Shared,
        consumer_name=consumer_name_arg,
        receiver_queue_size=1000,
        max_total_receiver_queue_size_across_partitions=50000
    )
    print(f"High-performance consumer created for topic: {TOPIC_NAME}")

    #--- Step 3: Consume Messages with End-to-End Latency ---
    print("\nStarting high-performance message consumption...")
    print("Press Ctrl+C to stop consuming...\n")
    
    messages_received = 0
    latencies = []
    
    while True:
        try:
            msg = consumer.receive(timeout_millis=5000)
            receive_time = time.time() * 1000
            
            send_timestamp = float(msg.properties().get('send_timestamp', receive_time))
            end_to_end_latency = receive_time - send_timestamp
            latencies.append(end_to_end_latency)
            
            message_bytes = msg.data()
            print(f"  Received {len(message_bytes)} bytes - E2E Latency: {end_to_end_latency:.2f}ms")
            
            consumer.acknowledge(msg)
            messages_received += 1
                
        except Exception as e:
            error_msg = str(e).lower()
            if "timeout" in error_msg or "timed out" in error_msg:
                continue
            elif "keyboard" in error_msg or "interrupted" in error_msg:
                print("\nReceived Ctrl+C. Stopping consumer...")
                break
            else:
                print(f"Error receiving message: {e}")
                time.sleep(1)
                continue

    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0
        
        print("\n--- End-to-End Latency Metrics ---")
        print(f"Total messages received: {messages_received}")
        print(f"Average E2E latency: {avg_latency:.2f}ms")
        print(f"Min E2E latency: {min_latency:.2f}ms")
        print(f"Max E2E latency: {max_latency:.2f}ms")
        print(f"P95 E2E latency: {p95_latency:.2f}ms")
        print(f"P99 E2E latency: {p99_latency:.2f}ms")
        
        if avg_latency < 10:
            print("✅ SUCCESS: Achieved target <10ms end-to-end latency!")
        else:
            print(f"⚠️  WARNING: Average E2E latency {avg_latency:.2f}ms exceeds 10ms target")
    else:
        print(f"\nTotal messages received: {messages_received}")

except KeyboardInterrupt:
    print("\nReceived Ctrl+C. Stopping consumer...")
    
except pulsar.exceptions.PulsarException as e:
    print(f"ERROR: Pulsar client exception occurred: {e}")
    print("Please ensure your Pulsar Docker containers are running correctly (`docker-compose ps`).")
    print("Also, check that port 6650 is not blocked or in use by another application.")

except Exception as e:
    print(f"ERROR: Unexpected error occurred: {e}")

finally:
    if consumer:
        consumer.close()
        print("Consumer closed.")
    
    if client:
        client.close()
        print("Pulsar Client closed.")

print("\n--- Consumer Finished ---")