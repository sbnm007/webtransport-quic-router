import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import matplotlib.dates as mdates
import os
import glob
import numpy as np

def load_all_csv_files(directory):
    """Load all CSV files from a directory and combine them"""
    csv_files = glob.glob(os.path.join(directory, "buffer_metrics_*.csv"))
    all_data = []
    
    for file in csv_files:
        df = pd.read_csv(file)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        # Add filename for identification
        df['source_file'] = os.path.basename(file)
        all_data.append(df)
    
    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)
        return combined_df
    else:
        return pd.DataFrame()

def plot_metrics_by_client(df, directory_name, metric_columns, plot_title, ylabel, filename_prefix):
    """Create plots separated by client"""
    if df.empty:
        print(f"No data found in {directory_name}")
        return
    
    # Get unique clients
    unique_clients = df['client_id'].unique()
    colors = plt.cm.tab10(np.linspace(0, 1, len(unique_clients)))
    
    plt.figure(figsize=(15, 8))
    
    for i, client in enumerate(unique_clients):
        client_data = df[df['client_id'] == client].sort_values('timestamp')
        
        for j, metric in enumerate(metric_columns):
            if metric in client_data.columns:
                if len(metric_columns) == 1:
                    label = f'Client {i+1}'
                else:
                    label = f'Client {i+1} - {metric.replace("_", " ").title()}'
                
                if len(metric_columns) == 1:
                    plt.plot(client_data['timestamp'], client_data[metric], 
                            label=label, marker='o', color=colors[i], alpha=0.8, 
                            markersize=3, linewidth=1.5)
                else:
                    linestyle = ['-', '--', '-.'][j % 3]
                    plt.plot(client_data['timestamp'], client_data[metric], 
                            label=label, marker='o', color=colors[i], 
                            linestyle=linestyle, alpha=0.8, markersize=3, linewidth=1.5)
    
    plt.title(f'{plot_title} - {directory_name.replace("-", " ").title()}')
    plt.xlabel('Time')
    plt.ylabel(ylabel)
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, alpha=0.3)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    plt.gca().xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Save plot
    output_filename = f'{filename_prefix}_{directory_name}.png'
    plt.savefig(output_filename, dpi=300, bbox_inches='tight')
    plt.show()
    print(f"Saved: {output_filename}")

def plot_aggregated_metrics(df, directory_name, metric_column, plot_title, ylabel, filename_prefix, aggregation_func='sum'):
    """Create plots with aggregated metrics across all clients"""
    if df.empty:
        print(f"No data found in {directory_name}")
        return
    
    # Group by timestamp and aggregate
    if aggregation_func == 'mean':
        aggregated = df.groupby('timestamp')[metric_column].mean().reset_index()
        agg_label = 'Average'
    else:
        aggregated = df.groupby('timestamp')[metric_column].sum().reset_index()
        agg_label = 'Total'
    
    plt.figure(figsize=(12, 6))
    plt.plot(aggregated['timestamp'], aggregated[metric_column], 
             label=f'{agg_label} {metric_column.replace("_", " ").title()}', 
             marker='o', linewidth=1.5, markersize=3)
    
    plt.title(f'{plot_title} - {directory_name.replace("-", " ").title()} (Aggregated)')
    plt.xlabel('Time')
    plt.ylabel(ylabel)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    plt.gca().xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Save plot
    output_filename = f'{filename_prefix}_aggregated_{directory_name}.png'
    plt.savefig(output_filename, dpi=300, bbox_inches='tight')
    plt.show()
    print(f"Saved: {output_filename}")

def main():
    # Directory to process (change this variable to process different directories)
    directory = 'five-clients'  # Change to 'five-clients' or other directory as needed
    
    if not os.path.exists(directory):
        print(f"Directory {directory} not found!")
        return
        
    print(f"\nProcessing directory: {directory}")
    
    # Load all CSV files from the directory
    df = load_all_csv_files(directory)
    
    if df.empty:
        print(f"No CSV files found in {directory}")
        return
        
    print(f"Found {len(df['client_id'].unique())} unique clients")
    time_diff = (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 60
    print(f"Time range: {time_diff:.1f} minutes")
    
    # Plot 1: Packet Processing Performance (individual clients)
    plot_metrics_by_client(
        df, directory, 
        ['packets_total', 'packets_complete', 'packets_fragmented'],
        'Packet Processing Performance Over Time',
        'Number of Packets',
        'packet_processing_by_client'
    )
    
    # Plot 2: Fragmentation Rate (individual clients)
    plot_metrics_by_client(
        df, directory,
        ['fragmentation_rate'],
        'Fragmentation Rate Over Time',
        'Fragmentation Rate',
        'fragmentation_by_client'
    )
    
    # Plot 3: Throughput (individual clients)
    plot_metrics_by_client(
        df, directory,
        ['throughput_mbps'],
        'Throughput Performance Over Time',
        'Throughput (Mbps)',
        'throughput_by_client'
    )
    
    # Plot 4: Aggregated Total Packets
    plot_aggregated_metrics(
        df, directory,
        'packets_total',
        'Total Packets Over Time',
        'Total Packets (All Clients)',
        'total_packets',
        'sum'
    )
    
    # Plot 5: Average Throughput
    plot_aggregated_metrics(
        df, directory,
        'throughput_mbps',
        'Average Throughput Over Time',
        'Average Throughput (Mbps)',
        'avg_throughput',
        'mean'
    )

if __name__ == "__main__":
    main()
