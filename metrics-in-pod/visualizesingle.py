import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import matplotlib.dates as mdates

# Read the CSV file
df = pd.read_csv('single-client-result/buffer_metrics_20250805_180450.csv')  # Replace with your CSV file path

# Convert timestamp to datetime
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Plot 1: Packet Processing Performance
plt.figure(figsize=(12, 6))
plt.plot(df['timestamp'], df['packets_total'], label='Total Packets', marker='o')
plt.plot(df['timestamp'], df['packets_complete'], label='Complete Packets', marker='s')
plt.plot(df['timestamp'], df['packets_fragmented'], label='Fragmented Packets', marker='^')
plt.title('Packet Processing Performance Over Time')
plt.xlabel('Time')
plt.ylabel('Number of Packets')
plt.legend()
plt.grid(True)
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.gca().xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('packet_processing_performance.png', dpi=300, bbox_inches='tight')
plt.show()

# Plot 2: Fragmentation Analysis
plt.figure(figsize=(12, 6))
plt.plot(df['timestamp'], df['fragmentation_rate'], label='Fragmentation Rate', marker='o', color='red')
plt.title('Fragmentation Analysis Over Time')
plt.xlabel('Time')
plt.ylabel('Fragmentation Rate')
plt.legend()
plt.grid(True)
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.gca().xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('fragmentation_analysis.png', dpi=300, bbox_inches='tight')
plt.show()

# Plot 3: Throughput Performance
plt.figure(figsize=(12, 6))
plt.plot(df['timestamp'], df['throughput_mbps'], label='Throughput (Mbps)', marker='o', color='green')
plt.title('Throughput Performance Over Time')
plt.xlabel('Time')
plt.ylabel('Throughput (Mbps)')
plt.legend()
plt.grid(True)
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.gca().xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('throughput_performance.png', dpi=300, bbox_inches='tight')
plt.show()