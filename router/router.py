#!/usr/bin/env python3
"""
WebTransport Router - Configuration-Driven Microservice Routing with Buffer Metrics
"""

import asyncio
import argparse
import logging
import os
import struct
import json
import time
import csv
import threading
from datetime import datetime
from pathlib import Path
import aiohttp
import yaml
import statistics
import psutil
from typing import Dict, Optional, Any
from aioquic.asyncio import serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, ConnectionTerminated, ProtocolNegotiated
from aioquic.h3.connection import H3Connection
from aioquic.h3.events import H3Event, HeadersReceived, DataReceived, WebTransportStreamDataReceived

#Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#Certificate paths (updated for local development)
CERT_PATH = os.getenv("CERT_PATH", "/certs/new-quic.crt")
KEY_PATH = os.getenv("KEY_PATH", "/certs/new-quic.key")
CONFIG_PATH = os.getenv("CONFIG_PATH", "/config/router_config.yaml")

class ServiceConfig:
    """Configuration for a service"""
    def __init__(self, config_dict: Dict[str, Any]):
        self.name = config_dict.get('name', '')
        self.host = config_dict.get('host', 'localhost')
        self.port = config_dict.get('port', 8080)
        self.endpoint = config_dict.get('endpoint', '/process')
        self.content_type = config_dict.get('content_type', 'application/octet-stream')
        self.timeout = config_dict.get('timeout', 30)
        self.retries = config_dict.get('retries', 3)
        self.custom_headers = config_dict.get('custom_headers', {})
        self.data_format = config_dict.get('data_format', 'binary')  #binary, json, form
        self.preprocessing = config_dict.get('preprocessing', {})
        self.enabled = config_dict.get('enabled', True)
        
    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}{self.endpoint}"

class ConfigManager:
    """Manages router configuration with hot-reload capability"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.services = {}
        self.global_config = {}
        self.last_modified = 0
        self.load_config()
        
    def load_config(self):
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                config_data = yaml.safe_load(f)
                
            self.global_config = config_data.get('global', {})
            services_config = config_data.get('services', {})
            
            #Load service configurations
            self.services = {}
            for service_name, service_config in services_config.items():
                self.services[service_name] = ServiceConfig(service_config)
                
            self.last_modified = os.path.getmtime(self.config_path)
            logger.info(f"✅ Configuration loaded: {len(self.services)} services")
            
            #Log loaded services
            for name, config in self.services.items():
                status = "✅" if config.enabled else "❌"
                logger.info(f"  {status} {name}: {config.url}")
                
        except Exception as e:
            logger.error(f"❌ Failed to load config: {e}")
            self._load_default_config()
    
    def _load_default_config(self):
        """Load minimal fallback configuration"""
        #Only set empty services and global defaults if config file is missing
        self.services = {}
        self.global_config = {
            'default_timeout': 30,
            'connect_timeout': 5,
            'log_level': 'INFO'
        }
        logger.warning("📝 No configuration file found - router will only process services defined in YAML config")
    
    def should_reload(self) -> bool:
        """Check if configuration should be reloaded"""
        try:
            if os.path.exists(self.config_path):
                return os.path.getmtime(self.config_path) > self.last_modified
            return False
        except:
            return False
    
    def get_service_config(self, service_name: str) -> Optional[ServiceConfig]:
        """Get configuration for a specific service"""
        return self.services.get(service_name)
    

class WebTransportRouter(QuicConnectionProtocol):
    """Configuration-driven WebTransport Router with Buffer Metrics"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._http = None
        self._alpn_negotiated = False
        self._wt_session_id = None
        self._stream_buffers = {}
        self._http_session = None
        
        #Configuration manager
        self.config_manager = ConfigManager(CONFIG_PATH)
        
        #Enhanced Statistics for Thesis Evaluation
        self.stats = {
            'packets_processed': 0,
            'packets_failed': 0,
            'services_called': {},
            'last_config_reload': time.time()
        }
        
        #Buffer Metrics for Thesis
        self.buffer_metrics = {
            'max_buffer_size': 0,
            'current_buffer_size': 0,
            'buffer_overflow_count': 0,
            'fragmented_packets': 0,
            'complete_packets': 0,
            'processing_times': [],
            'memory_usage': [],
            'concurrent_streams': 0,
            'stream_buffer_sizes': {},
            'packet_size_distribution': {},
            'buffer_wait_times': [],
            'total_bytes_buffered': 0,
            'max_concurrent_streams': 0
        }
        
        #Performance tracking
        self.performance_metrics = {
            'memory_samples': [],
            'cpu_samples': [],
            'throughput_samples': [],
            'latency_samples': []
        }
        
        #Add basic metrics to the comprehensive buffer_metrics
        self.buffer_metrics.update({
            'total_bytes': 0,
            'total_packets': 0,
            'packet_sizes': [],
            'buffered_streams': []
        })
        
        #Initialize throughput tracking
        self._last_throughput_check = time.time()
        self._last_bytes_count = 0
        
        #Start metrics collection
        asyncio.create_task(self._collect_system_metrics())
        
        #Initialize metrics logger
        self.metrics_logger = MetricsLogger()
        
        #Client tracking
        self.client_id = f"client_{id(self)}"  #Unique client identifier
        
        #Start background metrics logging task
        self.metrics_logging_task = None
        
    async def _initialize_http_session(self):
        """Initialize HTTP session for microservice communication"""
        if self._http_session is None:
            timeout = aiohttp.ClientTimeout(
                total=self.config_manager.global_config.get('default_timeout', 30),
                connect=self.config_manager.global_config.get('connect_timeout', 5)
            )
            self._http_session = aiohttp.ClientSession(timeout=timeout)
            logger.info("✓ HTTP session initialized for microservice communication")
    
    def _parse_packet_header(self, data: bytes) -> Optional[Dict]:
        """Parse the 32-byte packet header"""
        if len(data) < 32:
            return None
            
        try:
            #track_id (16 bytes)
            track_id = data[:16].rstrip(b'\x00').decode('utf-8')
            
            #payload_length (4 bytes, big endian)
            payload_length = struct.unpack('>I', data[16:20])[0]
            
            #track_type (12 bytes)
            track_type = data[20:32].rstrip(b'\x00').decode('utf-8')
            
            return {
                'track_id': track_id,
                'payload_length': payload_length,
                'track_type': track_type
            }
        except Exception as e:
            logger.error(f"Error parsing packet header: {e}")
            return None
    
    def quic_event_received(self, event: QuicEvent) -> None:
        """Handle QUIC events"""
        
        if isinstance(event, ProtocolNegotiated):
            logger.info(f"✓ ALPN negotiated: {event.alpn_protocol}")
            self._alpn_negotiated = True
            
            if event.alpn_protocol == "h3":
                self._http = H3Connection(self._quic, enable_webtransport=True)
                logger.info("HTTP/3 connection initialized with WebTransport support")
                
                #Start metrics logging when connection is established
                if self.metrics_logging_task is None:
                    asyncio.create_task(self.start_metrics_logging())
            else:
                logger.warning(f"Unexpected ALPN protocol: {event.alpn_protocol}")
                
        elif isinstance(event, ConnectionTerminated):
            logger.info(f"Connection terminated: error={event.error_code}, reason={event.reason_phrase}")
            asyncio.create_task(self._cleanup_connection())
            
        #Process HTTP/3 events only if we have a valid connection
        if self._http is not None:
            try:
                for http_event in self._http.handle_event(event):
                    self._handle_http_event(http_event)
            except Exception as e:
                logger.error(f"Error processing HTTP/3 event: {e}")
    
    def _handle_http_event(self, event: H3Event) -> None:
        """Handle HTTP/3 events"""
        
        if isinstance(event, HeadersReceived):
            headers = dict(event.headers)
            method = headers.get(b":method", b"").decode()
            protocol = headers.get(b":protocol", b"").decode()
            path = headers.get(b":path", b"").decode()
            
            logger.info(f"HTTP/3 request: {method} {path} (protocol: {protocol}) on stream {event.stream_id}")
            
            if method == "CONNECT" and protocol == "webtransport":
                logger.info("✓ WebTransport CONNECT request received")
                
                self._wt_session_id = event.stream_id
                
                self._http.send_headers(
                    stream_id=event.stream_id,
                    headers=[
                        (b":status", b"200"),
                        (b"sec-webtransport-http3-draft", b"draft02"),
                    ]
                )
                logger.info("✓ WebTransport session established")
                
            elif method == "GET" and path == "/metrics":
                #Export buffer metrics for thesis analysis
                logger.info("📊 Metrics export requested")
                metrics = self.export_buffer_metrics()
                response_data = json.dumps(metrics, indent=2).encode('utf-8')
                
                self._http.send_headers(
                    stream_id=event.stream_id,
                    headers=[
                        (b":status", b"200"),
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(response_data)).encode()),
                        (b"access-control-allow-origin", b"*"),
                    ]
                )
                self._http.send_data(stream_id=event.stream_id, data=response_data, end_stream=True)
                
            else:
                self._http.send_headers(
                    stream_id=event.stream_id,
                    headers=[
                        (b":status", b"404"),
                        (b"content-length", b"0")
                    ]
                )
                
        elif isinstance(event, WebTransportStreamDataReceived):
            logger.info(f"📡 WebTransport stream data: {len(event.data)} bytes on stream {event.stream_id}, stream_ended={event.stream_ended}")
            if len(event.data) > 0:
                self._handle_wt_stream_data(event.stream_id, event.data, event.stream_ended)
            
        elif isinstance(event, DataReceived):
            logger.info(f"📨 HTTP/3 data: {len(event.data)} bytes on stream {event.stream_id}")
            
            if len(event.data) > 0:
                if event.stream_id == self._wt_session_id:
                    logger.info("🔍 Processing HTTP/3 data as potential WebTransport session data")
                else:
                    if len(event.data) >= 32:
                        header_info = self._parse_packet_header(event.data[:32])
                        if header_info:
                            logger.info(f"🔍 Found valid packet header in HTTP/3 data: {header_info}")
                            self._handle_wt_stream_data(event.stream_id, event.data, False)

    def _handle_wt_stream_data(self, stream_id: int, data: bytes, stream_ended: bool, _recursive_call: bool = False):
        """Handle WebTransport stream data with comprehensive metrics"""
        
        #Skip processing if no data and stream not ended (but allow recursive calls)
        if len(data) == 0 and not stream_ended and not _recursive_call:
            return
            
        #Check for config reload
        if self.config_manager.should_reload():
            logger.info("🔄 Configuration changed, reloading...")
            self.config_manager.load_config()
            self.stats['last_config_reload'] = time.time()
        
        #Record packet arrival time for latency tracking
        packet_start_time = time.time()
        
        #Initialize stream buffer if new
        if stream_id not in self._stream_buffers:
            self._stream_buffers[stream_id] = b""
            self.buffer_metrics['concurrent_streams'] += 1
            self.buffer_metrics['max_concurrent_streams'] = max(
                self.buffer_metrics['max_concurrent_streams'],
                self.buffer_metrics['concurrent_streams']
            )
            
            #Track unique streams
            if stream_id not in self.buffer_metrics['buffered_streams']:
                self.buffer_metrics['buffered_streams'].append(stream_id)
            
            logger.debug(f"📊 New stream {stream_id}: Total active = {len(self._stream_buffers)}")
        
        #Record buffer state before adding data
        buffer_before = len(self._stream_buffers[stream_id])
        
        #Add new data to buffer
        self._stream_buffers[stream_id] += data
        buffer = self._stream_buffers[stream_id]
        
        #Update comprehensive buffer metrics
        bytes_added = len(data)
        if bytes_added > 0:  #Only count actual data
            self.buffer_metrics['total_bytes'] += bytes_added
            self.buffer_metrics['total_packets'] += 1
            self.buffer_metrics['packet_sizes'].append(bytes_added)
            self.buffer_metrics['total_bytes_buffered'] += bytes_added
        
        #Calculate current total buffer size across all streams
        current_total_buffer = sum(len(buf) for buf in self._stream_buffers.values())
        self.buffer_metrics['current_buffer_size'] = current_total_buffer
        self.buffer_metrics['max_buffer_size'] = max(
            self.buffer_metrics['max_buffer_size'],
            current_total_buffer
        )
        
        #Track buffer sizes per stream
        self.buffer_metrics['stream_buffer_sizes'][stream_id] = len(buffer)
        
        #Detect fragmentation (data arriving in multiple pieces)
        if buffer_before > 0 and bytes_added > 0:
            self.buffer_metrics['fragmented_packets'] += 1
            logger.debug(f"🧩 Fragment detected on stream {stream_id}: {bytes_added}B added to {buffer_before}B")
        
        #Record packet size distribution
        self._record_packet_size(bytes_added)
        
        #Check for potential buffer overflow
        if current_total_buffer > 10 * 1024 * 1024:  #10MB threshold
            self.buffer_metrics['buffer_overflow_count'] += 1
            logger.warning(f"🚨 Buffer overflow: {current_total_buffer:,}B across {len(self._stream_buffers)} streams")
        
        #Try to parse the packet header
        if len(buffer) >= 32:
            header_info = self._parse_packet_header(buffer[:32])
            if header_info:
                expected_payload_length = header_info['payload_length']
                total_packet_length = 32 + expected_payload_length
                
                #Check if we have the complete packet
                if len(buffer) >= total_packet_length:
                    payload = buffer[32:total_packet_length]
                    
                    #Record processing metrics
                    processing_time = time.time() - packet_start_time
                    self.buffer_metrics['processing_times'].append(processing_time)
                    self.buffer_metrics['complete_packets'] += 1
                    
                    logger.info(f"✅ Complete packet: {total_packet_length}B in {processing_time*1000:.2f}ms (Total processed: {self.buffer_metrics['complete_packets']})")
                    
                    #Process the packet using configuration
                    asyncio.create_task(self._process_media_packet(header_info, payload))
                    
                    #Remove processed packet from buffer
                    self._stream_buffers[stream_id] = buffer[total_packet_length:]
                    
                    #Update buffer metrics after removal
                    self.buffer_metrics['current_buffer_size'] = sum(
                        len(buf) for buf in self._stream_buffers.values()
                    )
                    self.buffer_metrics['stream_buffer_sizes'][stream_id] = len(self._stream_buffers[stream_id])
                    
                    #If there's more data, try to process it recursively
                    if len(self._stream_buffers[stream_id]) > 0:
                        self._handle_wt_stream_data(stream_id, b"", stream_ended, _recursive_call=True)
                else:
                    #Record buffer wait time for incomplete packets
                    wait_time = time.time() - packet_start_time
                    self.buffer_metrics['buffer_wait_times'].append(wait_time)
                    logger.debug(f"⏳ Buffering stream {stream_id}: have {len(buffer)}, need {total_packet_length}")
            else:
                logger.warning(f"❌ Failed to parse packet header for stream {stream_id} (buffer: {len(buffer)}B)")
        else:
            logger.debug(f"⏳ Waiting for header on stream {stream_id}: have {len(buffer)}, need 32 bytes")
        
        #Clean up ended streams
        if stream_ended:
            if stream_id in self._stream_buffers and len(self._stream_buffers[stream_id]) == 0:
                del self._stream_buffers[stream_id]
                if stream_id in self.buffer_metrics['stream_buffer_sizes']:
                    del self.buffer_metrics['stream_buffer_sizes'][stream_id]
                if self.buffer_metrics['concurrent_streams'] > 0:
                    self.buffer_metrics['concurrent_streams'] -= 1
                logger.info(f"🧹 Cleaned up ended stream {stream_id}")
    
    
    def _record_packet_size(self, size: int):
        """Record packet size for distribution analysis"""
        if size < 1024:
            self.buffer_metrics['packet_size_distribution']['small'] = \
                self.buffer_metrics['packet_size_distribution'].get('small', 0) + 1
        elif size < 5120:
            self.buffer_metrics['packet_size_distribution']['medium'] = \
                self.buffer_metrics['packet_size_distribution'].get('medium', 0) + 1
        elif size < 10240:
            self.buffer_metrics['packet_size_distribution']['large'] = \
                self.buffer_metrics['packet_size_distribution'].get('large', 0) + 1
        else:
            self.buffer_metrics['packet_size_distribution']['xlarge'] = \
                self.buffer_metrics['packet_size_distribution'].get('xlarge', 0) + 1
    
    async def _collect_system_metrics(self):
        """Continuously collect system performance metrics"""
        while True:
            try:
                #Try to get process info (psutil may not be available)
                try:
                    import psutil
                    process = psutil.Process()
                    memory_mb = process.memory_info().rss / 1024 / 1024
                    cpu_percent = process.cpu_percent()
                except ImportError:
                    memory_mb = 0  #Fallback if psutil not available
                    cpu_percent = 0
                
                #Collect metrics
                self.performance_metrics['memory_samples'].append({
                    'timestamp': time.time(),
                    'memory_mb': memory_mb,
                    'buffer_size': self.buffer_metrics['current_buffer_size'],
                    'active_streams': len(self._stream_buffers),
                    'concurrent_streams': self.buffer_metrics['concurrent_streams']
                })
                
                self.performance_metrics['cpu_samples'].append({
                    'timestamp': time.time(),
                    'cpu_percent': cpu_percent
                })
                
                #Calculate throughput
                current_time = time.time()
                if hasattr(self, '_last_throughput_check'):
                    time_diff = current_time - self._last_throughput_check
                    bytes_diff = self.buffer_metrics['total_bytes_buffered'] - self._last_bytes_count
                    throughput_mbps = (bytes_diff / time_diff) / (1024 * 1024) if time_diff > 0 else 0
                    
                    self.performance_metrics['throughput_samples'].append({
                        'timestamp': current_time,
                        'throughput_mbps': throughput_mbps
                    })
                
                self._last_throughput_check = current_time
                self._last_bytes_count = self.buffer_metrics['total_bytes_buffered']
                
                #Keep only last 1000 samples
                for metric_list in ['memory_samples', 'cpu_samples', 'throughput_samples']:
                    samples = self.performance_metrics[metric_list]
                    if len(samples) > 1000:
                        self.performance_metrics[metric_list] = samples[-1000:]
                        
            except Exception as e:
                logger.debug(f"Metrics collection error: {e}")
                
            await asyncio.sleep(1)  #Collect every second
    
    def export_buffer_metrics(self) -> dict:
        """Export only the most essential buffer metrics for thesis analysis"""
        
        #Calculate key values
        complete_packets = self.buffer_metrics.get('complete_packets', 0)
        fragmented_packets = self.buffer_metrics.get('fragmented_packets', 0)
        total_packets = complete_packets + fragmented_packets
        
        #Debug logging
        logger.info(f"📊 Exporting metrics: complete={complete_packets}, fragmented={fragmented_packets}, total_bytes={self.buffer_metrics.get('total_bytes', 0)}")
        
        #Core metrics only
        metrics = {
            #Buffer state
            'buffer_size_bytes': self.buffer_metrics.get('current_buffer_size', 0),
            'max_buffer_size_bytes': self.buffer_metrics.get('max_buffer_size', 0),
            'buffer_overflows': self.buffer_metrics.get('buffer_overflow_count', 0),
            
            #Packet processing
            'packets_total': total_packets,
            'packets_complete': complete_packets,
            'packets_fragmented': fragmented_packets,
            'fragmentation_rate': round(fragmented_packets / max(1, total_packets), 3),
            
            #Stream management
            'streams_active': len(self._stream_buffers),
            'streams_max_concurrent': self.buffer_metrics.get('max_concurrent_streams', 0),
            
            #Services
            'services_called': dict(self.stats.get('services_called', {})),
            
            #Add raw counters for debugging
            'total_bytes_received': self.buffer_metrics.get('total_bytes', 0),
            'total_packets_received': self.buffer_metrics.get('total_packets', 0)
        }
        
        #Add timing metrics only if we have data
        processing_times = self.buffer_metrics.get('processing_times', [])
        if processing_times:
            metrics['avg_processing_time_ms'] = round((sum(processing_times) / len(processing_times)) * 1000, 2)
            metrics['max_processing_time_ms'] = round(max(processing_times) * 1000, 2)
        
        wait_times = self.buffer_metrics.get('buffer_wait_times', [])
        if wait_times:
            metrics['avg_buffer_wait_ms'] = round((sum(wait_times) / len(wait_times)) * 1000, 2)
            metrics['max_buffer_wait_ms'] = round(max(wait_times) * 1000, 2)
        
        #Current memory
        memory_samples = self.performance_metrics.get('memory_samples', [])
        if memory_samples and memory_samples[-1]['memory_mb'] > 0:
            metrics['memory_mb'] = round(memory_samples[-1]['memory_mb'], 1)
        
        #Packet size distribution (only if non-empty)
        size_dist = self.buffer_metrics.get('packet_size_distribution', {})
        if size_dist:
            metrics['packet_sizes'] = size_dist
            
        return metrics
    
    def export_performance_metrics(self) -> Dict[str, Any]:
        """Export performance metrics for logging"""
        return {
            'memory_samples': self.performance_metrics.get('memory_samples', []),
            'cpu_samples': self.performance_metrics.get('cpu_samples', []),
            'throughput_samples': self.performance_metrics.get('throughput_samples', [])
        }
    
    async def _process_media_packet(self, header_info: Dict, payload: bytes):
        """Process a complete media packet using configuration"""
        track_id = header_info['track_id']
        track_type = header_info['track_type']
        payload_length = header_info['payload_length']
        
        logger.info(f"📦 Received {track_type} packet: track_id='{track_id}', payload={payload_length} bytes")
        
        #Get service configuration
        service_config = self.config_manager.get_service_config(track_type)
        
        if not service_config:
            logger.warning(f"❌ No configuration found for track type: {track_type}")
            self.stats['packets_failed'] += 1
            return
        
        if not service_config.enabled:
            logger.info(f"⏸️ Service {track_type} is disabled, skipping")
            return
        
        #Initialize HTTP session if needed
        await self._initialize_http_session()
        
        #Route to configured service
        try:
            await self._proxy_to_service(service_config, header_info, payload)
            self.stats['packets_processed'] += 1
            
            #Update service call statistics
            if track_type not in self.stats['services_called']:
                self.stats['services_called'][track_type] = 0
            self.stats['services_called'][track_type] += 1
            
        except Exception as e:
            logger.error(f"❌ Failed to route {track_type} packet: {e}")
            self.stats['packets_failed'] += 1

    async def _proxy_to_service(self, service_config: ServiceConfig, header_info: Dict, payload: bytes):
        """Generic proxy method for any configured service"""
        
        #Prepare common headers
        headers = {
            "X-Track-ID": header_info['track_id'],
            "X-Track-Type": header_info['track_type'],
            "X-Payload-Length": str(header_info['payload_length']),
            "X-Timestamp": str(int(time.time() * 1000))
        }
        
        #Add custom headers from configuration
        headers.update(service_config.custom_headers)
        
        #Prepare data based on format
        if service_config.data_format == 'json':
            if service_config.content_type == 'application/json':
                #For chat or other JSON services
                try:
                    data = json.loads(payload.decode('utf-8'))
                    request_data = {
                        "track_id": header_info['track_id'],
                        "track_type": header_info['track_type'],
                        "payload_length": header_info['payload_length'],
                        "timestamp": int(time.time() * 1000),
                        "data": data
                    }
                    headers["Content-Type"] = "application/json"
                    data_to_send = json.dumps(request_data)
                except json.JSONDecodeError:
                    logger.error(f"❌ Failed to parse JSON payload for {service_config.name}")
                    return
            else:
                data_to_send = payload
        else:
            #Binary format
            headers["Content-Type"] = service_config.content_type
            data_to_send = payload
        
        #Make request with retry logic
        for attempt in range(service_config.retries + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=service_config.timeout)
                if service_config.data_format == 'json' and service_config.content_type == 'application/json':
                    async with self._http_session.post(
                        service_config.url,
                        data=data_to_send,
                        headers=headers,
                        timeout=timeout
                    ) as response:
                        await self._handle_service_response(service_config, response)
                        return
                else:
                    async with self._http_session.post(
                        service_config.url,
                        data=data_to_send,
                        headers=headers,
                        timeout=timeout
                    ) as response:
                        await self._handle_service_response(service_config, response)
                        return
                        
            except Exception as e:
                if attempt < service_config.retries:
                    logger.warning(f"⚠️ Retry {attempt + 1}/{service_config.retries} for {service_config.name}: {e}")
                    await asyncio.sleep(0.1 * (attempt + 1))  #Exponential backoff
                else:
                    logger.error(f"❌ Failed to proxy to {service_config.name} after {service_config.retries} retries: {e}")
                    raise
    
    async def _handle_service_response(self, service_config: ServiceConfig, response: aiohttp.ClientResponse):
        """Handle response from service"""
        if response.status == 200:
            try:
                result = await response.json()
                logger.info(f"✅ {service_config.name} service response: {result}")
            except:
                text = await response.text()
                logger.info(f"✅ {service_config.name} service response: {text}")
        else:
            error_text = await response.text()
            logger.error(f"❌ {service_config.name} service error {response.status}: {error_text}")

    async def start_metrics_logging(self):
        """Start the background metrics logging task"""
        if self.metrics_logging_task is None:
            self.metrics_logging_task = asyncio.create_task(self._metrics_logging_loop())
            logger.info(f"📊 Started background metrics logging for {self.client_id}")
            
            #Log connection established event
            self.metrics_logger.log_custom_event("CONNECTION", f"WebTransport connection established for {self.client_id}")
    
    async def stop_metrics_logging(self):
        """Stop the background metrics logging task"""
        if self.metrics_logging_task:
            self.metrics_logging_task.cancel()
            try:
                await self.metrics_logging_task
            except asyncio.CancelledError:
                pass
            self.metrics_logging_task = None
            logger.info(f"📊 Stopped background metrics logging for {self.client_id}")
            
            #Log connection terminated event
            self.metrics_logger.log_custom_event("CONNECTION", f"WebTransport connection terminated for {self.client_id}")
    
    async def _metrics_logging_loop(self):
        """Background task to log metrics every 5 seconds with client identification"""
        try:
            while True:
                #Export current metrics
                buffer_metrics = self.export_buffer_metrics()
                performance_metrics = self.export_performance_metrics()
                
                #Log to CSV with client ID
                self.metrics_logger.log_metrics(
                    buffer_metrics, 
                    performance_metrics, 
                    client_id=self.client_id
                )
                
                #Wait 5 seconds before next log
                await asyncio.sleep(5)
                
        except asyncio.CancelledError:
            logger.info(f"📊 Metrics logging loop cancelled for {self.client_id}")
        except Exception as e:
            logger.error(f"❌ Error in metrics logging loop for {self.client_id}: {e}")

    async def _cleanup_connection(self):
        """Clean up connection resources"""
        #Stop metrics logging
        await self.stop_metrics_logging()
        
        if self._http_session:
            await self._http_session.close()
            self._http_session = None
            logger.info("🧹 HTTP session closed")

    def get_all_services(self) -> Dict[str, ServiceConfig]:
        """Get all service configurations"""
        return self.services

class MetricsLogger:
    """Real-time metrics logger for thesis evaluation"""
    
    def __init__(self, log_dir: str = "metrics_logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        #Create timestamped filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_file = self.log_dir / f"buffer_metrics_{timestamp}.csv"
        self.event_log_file = self.log_dir / f"buffer_events_{timestamp}.log"
        
        #Initialize CSV with headers
        self._init_csv_file()
        
        #Track last values for event detection
        self.last_values = {}
        
        logger.info(f"📊 Metrics logging initialized: {self.csv_file}")
        logger.info(f"📊 Event logging initialized: {self.event_log_file}")
    
    def _init_csv_file(self):
        """Initialize CSV file with column headers"""
        headers = [
            'timestamp', 'client_id', 'buffer_size_bytes', 'max_buffer_size_bytes', 
            'buffer_overflows', 'packets_total', 'packets_complete', 
            'packets_fragmented', 'fragmentation_rate', 'streams_active', 
            'streams_max_concurrent', 'throughput_mbps', 'avg_processing_time_ms', 
            'avg_buffer_wait_ms'
        ]
        
        with open(self.csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
    
    def log_metrics(self, router_metrics: dict, performance_data: dict = None, client_id: str = "default"):
        """Log metrics to CSV file with client identification"""
        timestamp = datetime.now().isoformat()
        
        #Get performance data (only throughput)
        throughput_mbps = 0
        
        if performance_data:
            throughput_samples = performance_data.get('throughput_samples', [])
            if throughput_samples:
                throughput_mbps = throughput_samples[-1].get('throughput_mbps', 0)
        
        #Prepare CSV row without CPU and memory
        row = [
            timestamp,
            client_id,  #Add client identification
            router_metrics.get('buffer_size_bytes', 0),
            router_metrics.get('max_buffer_size_bytes', 0),
            router_metrics.get('buffer_overflows', 0),
            router_metrics.get('packets_total', 0),
            router_metrics.get('packets_complete', 0),
            router_metrics.get('packets_fragmented', 0),
            router_metrics.get('fragmentation_rate', 0),
            router_metrics.get('streams_active', 0),
            router_metrics.get('streams_max_concurrent', 0),
            round(throughput_mbps, 4),
            router_metrics.get('avg_processing_time_ms', 0),
            router_metrics.get('avg_buffer_wait_ms', 0)
        ]
        
        #Write to CSV
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)
        
        #Check for significant events to log
        self._check_and_log_events(router_metrics, timestamp, client_id)
    
    def _check_and_log_events(self, metrics: dict, timestamp: str, client_id: str = "default"):
        """Check for significant buffer events and log them with client ID"""
        events = []
        
        #Buffer overflow detection
        overflows = metrics.get('buffer_overflows', 0)
        last_key = f"{client_id}_buffer_overflows"
        if overflows > self.last_values.get(last_key, 0):
            events.append(f"BUFFER_OVERFLOW: Client={client_id}, Count increased to {overflows}")
        
        #High fragmentation detection
        frag_rate = metrics.get('fragmentation_rate', 0)
        if frag_rate > 0.5:  #More than 50% fragmented
            events.append(f"HIGH_FRAGMENTATION: Client={client_id}, Rate={frag_rate:.3f}")
        
        #Large buffer size detection
        buffer_size = metrics.get('buffer_size_bytes', 0)
        if buffer_size > 5 * 1024 * 1024:  #5MB threshold
            events.append(f"LARGE_BUFFER: Client={client_id}, Size={buffer_size:,} bytes")
        
        #High concurrent streams
        active_streams = metrics.get('streams_active', 0)
        if active_streams > 10:
            events.append(f"HIGH_STREAM_COUNT: Client={client_id}, Active={active_streams}")
        
        #Log events
        if events:
            with open(self.event_log_file, 'a') as f:
                for event in events:
                    f.write(f"{timestamp} - {event}\n")
        
        #Update last values with client-specific keys
        for key, value in metrics.items():
            self.last_values[f"{client_id}_{key}"] = value
    
    def log_custom_event(self, event_type: str, description: str):
        """Log a custom event"""
        timestamp = datetime.now().isoformat()
        with open(self.event_log_file, 'a') as f:
            f.write(f"{timestamp} - {event_type}: {description}\n")

def parse_arguments():
    """Parse command-line arguments for QUIC configuration"""
    parser = argparse.ArgumentParser(
        description="WebTransport Router - Configuration-Driven Microservice Routing",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="Use --examples to see usage examples for different scenarios."
    )
    
    #Examples
    parser.add_argument(
        "--examples",
        action="store_true",
        help="Show usage examples and exit"
    )
    
    #Server configuration
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind the server to"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=4433,
        help="Port to bind the server to"
    )
    
    #QUIC Flow Control Parameters
    parser.add_argument(
        "--max-data",
        type=int,
        default=1048576,  #1MB default
        help="Maximum amount of unacknowledged data for the entire connection (bytes)"
    )
    parser.add_argument(
        "--max-stream-data",
        type=int,
        default=262144,  #256KB default
        help="Maximum amount of unacknowledged data for each individual stream (bytes)"
    )
    parser.add_argument(
        "--max-datagram-size",
        type=int,
        default=3000,  #Safe default for most networks
        help="Maximum size for a single datagram/packet (bytes)"
    )
    
    #Additional QUIC Parameters
    parser.add_argument(
        "--max-stream-data-bidi-local",
        type=int,
        help="Maximum stream data for locally-initiated bidirectional streams (defaults to --max-stream-data)"
    )
    parser.add_argument(
        "--max-stream-data-bidi-remote",
        type=int,
        help="Maximum stream data for remotely-initiated bidirectional streams (defaults to --max-stream-data)"
    )
    parser.add_argument(
        "--max-stream-data-uni",
        type=int,
        help="Maximum stream data for unidirectional streams (defaults to --max-stream-data)"
    )
    
    #Certificate and config paths
    parser.add_argument(
        "--cert-path",
        default=CERT_PATH,
        help="Path to TLS certificate file"
    )
    parser.add_argument(
        "--key-path",
        default=KEY_PATH,
        help="Path to TLS private key file"
    )
    parser.add_argument(
        "--config-path",
        default=CONFIG_PATH,
        help="Path to router configuration YAML file"
    )
    
    #Logging
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    parser.add_argument(
        "--enable-keylog",
        action="store_true",
        help="Enable TLS key logging for debugging"
    )
    
    args = parser.parse_args()
    
    #Handle examples request
    if args.examples:
        print_usage_examples()
        exit(0)
    
    return args

def print_usage_examples():
    """Print usage examples for different scenarios"""
    print("\n" + "="*60)
    print("USAGE EXAMPLES")
    print("="*60)
    print("\n1. Basic server with default settings:")
    print("   python router.py")
    
    print("\n2. High-throughput configuration (for large file transfers):")
    print("   python router.py --max-data 10485760 --max-stream-data 2097152 --max-datagram-size 1452")
    print("   #10MB connection, 2MB per stream, 1452-byte packets")
    
    print("\n3. Low-latency configuration (for real-time data):")
    print("   python router.py --max-data 524288 --max-stream-data 131072 --max-datagram-size 1200")
    print("   #512KB connection, 128KB per stream, 1200-byte packets")
    
    print("\n4. Custom host/port with TLS key logging:")
    print("   python router.py --host 192.168.1.100 --port 8443 --enable-keylog")
    
    print("\n5. Different stream limits for different directions:")
    print("   python router.py \\")
    print("     --max-data 2097152 \\")
    print("     --max-stream-data-bidi-local 524288 \\")
    print("     --max-stream-data-bidi-remote 262144 \\")
    print("     --max-stream-data-uni 131072")
    
    print("\n6. Custom certificates and config:")
    print("   python router.py \\")
    print("     --cert-path /path/to/server.crt \\")
    print("     --key-path /path/to/server.key \\")
    print("     --config-path /path/to/router_config.yaml")
    
    print("\n" + "="*60)
    print("PARAMETER GUIDELINES")
    print("="*60)
    print("• max-data: Total unacknowledged data for entire connection")
    print("  - Small (128KB-512KB): Low memory usage, may limit throughput")
    print("  - Medium (1MB-4MB): Balanced performance")
    print("  - Large (10MB+): High throughput, more memory usage")
    
    print("\n• max-stream-data: Unacknowledged data per individual stream")
    print("  - Usually 1/4 to 1/2 of max-data")
    print("  - Smaller values provide better fairness between streams")
    
    print("\n• max-datagram-size: Maximum single packet size")
    print("  - 1200: Safe for most networks (recommended)")
    print("  - 1452: Ethernet MTU minus headers")
    print("  - Larger values may cause fragmentation")
    print("="*60 + "\n")

async def main():
    """Main server function"""
    
    #Parse command-line arguments
    args = parse_arguments()
    
    #Configure logging
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    #Update global configuration paths
    global CERT_PATH, KEY_PATH, CONFIG_PATH
    CERT_PATH = args.cert_path
    KEY_PATH = args.key_path
    CONFIG_PATH = args.config_path
    
    #Create default config if it doesn't exist
    ConfigManager(CONFIG_PATH)
    if not os.path.exists(CONFIG_PATH):
        logger.info("📝 No configuration file found, one will be created automatically")
    
    logger.info(f"🚀 Starting Configuration-Driven WebTransport Router on {args.host}:{args.port}")
    logger.info(f"📁 Configuration file: {CONFIG_PATH}")
    logger.info("🔧 QUIC Parameters:")
    logger.info(f"   Max Data: {args.max_data:,} bytes")
    logger.info(f"   Max Stream Data: {args.max_stream_data:,} bytes")
    logger.info(f"   Max Datagram Size: {args.max_datagram_size:,} bytes")
    
    #QUIC configuration
    configuration = QuicConfiguration(is_client=False)
    configuration.alpn_protocols = ["h3"]
    
    #Apply flow control parameters
    configuration.max_data = args.max_data
    configuration.max_stream_data_bidi_local = args.max_stream_data_bidi_local or args.max_stream_data
    configuration.max_stream_data_bidi_remote = args.max_stream_data_bidi_remote or args.max_stream_data
    configuration.max_stream_data_uni = args.max_stream_data_uni or args.max_stream_data
    configuration.max_datagram_frame_size = args.max_datagram_size
    
    logger.info(f"   Applied Max Data: {configuration.max_data:,} bytes")
    logger.info(f"   Applied Max Stream Data (Bidi Local): {configuration.max_stream_data_bidi_local:,} bytes")
    logger.info(f"   Applied Max Stream Data (Bidi Remote): {configuration.max_stream_data_bidi_remote:,} bytes")
    logger.info(f"   Applied Max Stream Data (Uni): {configuration.max_stream_data_uni:,} bytes")
    logger.info(f"   Applied Max Datagram Size: {configuration.max_datagram_frame_size:,} bytes")
    
    #Load certificates
    try:
        configuration.load_cert_chain(CERT_PATH, KEY_PATH)
        logger.info("✅ Certificates loaded successfully")
    except Exception as e:
        logger.error(f"❌ Failed to load certificates: {e}")
        return
    
    #Enable TLS key logging for debugging if requested
    if args.enable_keylog:
        keylog_file = os.path.join(os.getcwd(), "tls_keys_router.log")
        with open(keylog_file, "a") as f:
            configuration.secrets_log_file = f
            logger.info(f"🔍 TLS key logging enabled: {keylog_file}")
        
        #Start server
        try:
            await serve(
                args.host,
                args.port,
                configuration=configuration,
                create_protocol=WebTransportRouter
            )
            
            logger.info("✅ Configuration-Driven WebTransport Router is running!")
            logger.info(f"🔗 Connect to: https://{args.host}:{args.port}/wt")
            logger.info("🔄 Configuration hot-reload enabled")
            logger.info("⏹️  Press Ctrl+C to stop")
            
            #Keep running
            await asyncio.Future()
            
        except KeyboardInterrupt:
            logger.info("🛑 Server stopped by user")
        except Exception as e:
            logger.error(f"❌ Server error: {e}")
    else:
        #Start server without keylog
        try:
            await serve(
                args.host,
                args.port,
                configuration=configuration,
                create_protocol=WebTransportRouter
            )
            
            logger.info("✅ Configuration-Driven WebTransport Router is running!")
            logger.info(f"🔗 Connect to: https://{args.host}:{args.port}/wt")
            logger.info("🔄 Configuration hot-reload enabled")
            logger.info("⏹️  Press Ctrl+C to stop")
            
            #Keep running
            await asyncio.Future()
            
        except KeyboardInterrupt:
            logger.info("🛑 Server stopped by user")
        except Exception as e:
            logger.error(f"❌ Server error: {e}")

if __name__ == "__main__":
    asyncio.run(main())