#!/usr/bin/env python3
"""
HTTP Microservice - Receives data from WebTransport Router and sends to Pulsar
"""

import asyncio
import logging
import json
import time
import sys
import os
import yaml #Import yaml for reading config file
from aiohttp import web
import pulsar
from typing import Dict, Any #Import Dict and Any from typing

#--- Global Configuration Variables ---
#These will be populated by the MicroserviceConfigManager from the local config file
PULSAR_BROKER_URL = None
SEND_TO_PULSAR = False
MICROSERVICE_CONFIG_PATH = os.getenv("MICROSERVICE_CONFIG_PATH", "microservice_config.yaml")

#Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

#Global Pulsar client and producer (initialized in main)
pulsar_client = None
producer = None #This will be set dynamically based on service_name
current_service_name = "" #To be set by main

class MicroserviceConfig:
    """Configuration for this specific microservice"""
    def __init__(self, config_dict: Dict[str, Any]):
        self.pulsar_broker_url = config_dict.get('pulsar_broker_url', 'pulsar://localhost:6650')
        self.send_to_pulsar = str(config_dict.get('send_to_pulsar', 'False')).lower() == 'true'

class MicroserviceConfigManager:
    """Manages microservice configuration with hot-reload capability"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = None
        self.last_modified = 0
        self.load_config()

    def load_config(self):
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                config_data = yaml.safe_load(f)

            self.config = MicroserviceConfig(config_data)
            self.last_modified = os.path.getmtime(self.config_path)
            logger.info(f"✅ Microservice configuration loaded from {self.config_path}")

        except Exception as e:
            logger.error(f"❌ Failed to load microservice config from {self.config_path}: {e}", exc_info=True)
            #Fallback to default values if config file is missing or invalid
            self.config = MicroserviceConfig({})
            logger.warning("📝 Using default microservice configuration.")

    def should_reload(self) -> bool:
        """Check if configuration file should be reloaded"""
        try:
            if os.path.exists(self.config_path):
                return os.path.getmtime(self.config_path) > self.last_modified
            return False
        except:
            return False

class GenericServiceHandler:
    """Generic handler for all microservices"""

    def __init__(self, service_name: str): #Removed producer_instance here
        self.service_name = service_name
        self.packet_count = 0
        self.total_bytes = 0
        self.start_time = time.time()
        logger.info(f"✨ Initialized GenericServiceHandler for {self.service_name.upper()}")

    def log_packet_stats(self, payload_size: int):
        """Log packet statistics"""
        self.packet_count += 1
        self.total_bytes += payload_size

        #Calculate stats
        elapsed_time = time.time() - self.start_time
        avg_packet_size = self.total_bytes / self.packet_count if self.packet_count > 0 else 0
        packets_per_second = self.packet_count / elapsed_time if elapsed_time > 0 else 0
        bytes_per_second = self.total_bytes / elapsed_time if elapsed_time > 0 else 0

        #Log every 10 packets or if it's the first packet
        if self.packet_count % 10 == 0 or self.packet_count == 1:
            logger.info(f"📊 [{self.service_name.upper()}] Stats:")
            logger.info(f"  Packets: {self.packet_count}")
            logger.info(f"  Total Bytes: {self.total_bytes:,}")
            logger.info(f"  Avg Packet Size: {avg_packet_size:.1f} bytes")
            logger.info(f"  Packets/sec: {packets_per_second:.1f}")
            logger.info(f"  Bytes/sec: {bytes_per_second:,.1f}")

    async def process_data(self, request):
        """Process incoming data for any service type"""
        try:
            #current_service_name is a global variable
            
            #Get common headers
            track_id = request.headers.get('X-Track-ID', 'unknown')
            track_type = request.headers.get('X-Track-Type', 'unknown')
            payload_length_header = int(request.headers.get('X-Payload-Length', '0'))

            payload_data = None
            pulsar_payload = None
            pulsar_properties = {
                "track_id": track_id,
                "track_type": track_type,
                "timestamp": str(time.time()),
                "service_type": current_service_name
            }

            if current_service_name == "chat":
                #Chat messages are expected to be JSON
                payload_data = await request.json()
                message_content = payload_data.get('message', 'N/A')
                user_info = payload_data.get('user', 'N/A')
                message_timestamp = payload_data.get('timestamp', 'N/A')

                self.packet_count += 1 #Using generic packet_count for simplicity
                pulsar_payload = json.dumps(payload_data).encode('utf-8')
                pulsar_properties["message_id"] = str(self.packet_count)

                logger.info(f"💬 [{current_service_name.upper()}] Received chat message #{self.packet_count}")
                logger.info(f"  Track ID: {track_id}")
                logger.info(f"  Track Type: {track_type}")
                logger.info(f"  Message: {message_content}")
                logger.info(f"  User: {user_info}")
                logger.info(f"  Message Timestamp: {message_timestamp}")
                logger.info(f"  Processed At: {time.strftime('%H:%M:%S.%f')[:-3]}")

            else:
                #Other services (video, audio, screen, file) are expected to be binary
                payload_data = await request.read()
                self.packet_count += 1 #Using generic packet_count for simplicity
                pulsar_payload = payload_data

                #Add specific properties based on service type
                if current_service_name == "video":
                    pulsar_properties["frame_id"] = str(self.packet_count)
                    logger.info(f"🎥 [{current_service_name.upper()}] Received video frame #{self.packet_count}")
                elif current_service_name == "audio":
                    pulsar_properties["chunk_id"] = str(self.packet_count)
                    logger.info(f"🎵 [{current_service_name.upper()}] Received audio chunk #{self.packet_count}")
                elif current_service_name == "screen":
                    pulsar_properties["screen_update_id"] = str(self.packet_count)
                    logger.info(f"🖥️ [{current_service_name.upper()}] Received screen update #{self.packet_count}")
                elif current_service_name == "file":
                    pulsar_properties["file_chunk_id"] = str(self.packet_count)
                    logger.info(f"📁 [{current_service_name.upper()}] Received file chunk #{self.packet_count}")

                logger.info(f"  Track ID: {track_id}")
                logger.info(f"  Track Type: {track_type}")
                logger.info(f"  Payload Length (Header): {payload_length_header:,} bytes")
                logger.info(f"  Actual Payload Size: {len(payload_data):,} bytes")
                logger.info(f"  Timestamp: {time.strftime('%H:%M:%S.%f')[:-3]}")

            #Log packet stats
            self.log_packet_stats(len(pulsar_payload))

            #Send to Pulsar topic if enabled (using global SEND_TO_PULSAR and producer)
            if SEND_TO_PULSAR and producer: #Use global producer
                topic_name = f"persistent://public/default/{current_service_name}-topic"
                logger.info(f"Sending to Pulsar topic: {topic_name} with properties: {pulsar_properties}")
                producer.send(
                    pulsar_payload,
                    properties=pulsar_properties
                )
            else:
                logger.info("Pulsar sending is disabled or producer not initialized. Data only logged.")

            #Simulate processing time
            await asyncio.sleep(0.001)  #1ms processing time

            return web.json_response({
                'status': 'success',
                'service': current_service_name,
                'packet_id': self.packet_count,
                'track_id': track_id,
                'payload_size': len(pulsar_payload),
                'processed_at': time.time()
            })

        except Exception as e:
            logger.error(f"❌ [{current_service_name.upper()}] Error processing data: {e}", exc_info=True)
            return web.json_response({
                'status': 'error',
                'service': current_service_name,
                'error': str(e)
            }, status=500)

def create_app(service_name: str) -> web.Application: #Removed producer_instance here
    """Create web application for the service"""

    app = web.Application()
    handler = GenericServiceHandler(service_name) #Pass service_name only

    #All services will use a generic endpoint based on their name
    app.router.add_post(f'/process_{service_name}', handler.process_data)

    #Add health check endpoint
    async def health_check(request):
        return web.json_response({
            'status': 'healthy',
            'service': service_name,
            'uptime': time.time() - handler.start_time,
            'packets_processed': handler.packet_count,
            'total_bytes': handler.total_bytes,
            'pulsar_sending_enabled': SEND_TO_PULSAR #Use global SEND_TO_PULSAR
        })

    app.router.add_get('/health', health_check)

    return app

async def _reinitialize_pulsar_producer(new_pulsar_url: str, new_send_flag: bool, service_name: str):
    """Helper to reinitialize Pulsar client and producer based on new config."""
    global pulsar_client, producer, PULSAR_BROKER_URL, SEND_TO_PULSAR

    #Only reinitialize if there's an actual change in URL or send flag
    if new_pulsar_url == PULSAR_BROKER_URL and new_send_flag == SEND_TO_PULSAR:
        return

    logger.info("🔄 Reinitializing Pulsar client and producer due to config change...")

    #Close existing producer and client if they exist
    if producer:
        producer.close()
        logger.info("Pulsar producer closed.")
    if pulsar_client:
        pulsar_client.close()
        logger.info("Pulsar client closed.")

    pulsar_client = None
    producer = None
    PULSAR_BROKER_URL = new_pulsar_url
    SEND_TO_PULSAR = new_send_flag

    if SEND_TO_PULSAR:
        try:
            if not PULSAR_BROKER_URL:
                logger.error("❌ PULSAR_BROKER_URL is not set after reload. Cannot connect to Pulsar.")
                SEND_TO_PULSAR = False #Ensure it's disabled if URL is missing
            else:
                pulsar_client = pulsar.Client(PULSAR_BROKER_URL)
                topic_for_service = f"persistent://public/default/{service_name}-topic"
                producer = pulsar_client.create_producer(
                    topic_for_service,
                    batching_enabled=False,
                    send_timeout_millis=30000,
                    producer_name=f"{service_name}-microservice-producer",
                    compression_type=pulsar.CompressionType.NONE,
                    block_if_queue_full=True,
                    max_pending_messages=1000
                )
                logger.info(f"✅ Pulsar producer created for topic: {topic_for_service}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Pulsar or create producer after reload: {e}", exc_info=True)
            logger.warning("Disabling Pulsar sending due to connection error after reload.")
            SEND_TO_PULSAR = False
            producer = None
    else:
        logger.info("Pulsar sending is disabled by configuration.")


async def main():
    """Main service function"""
    global current_service_name #Declare global to modify it

    if len(sys.argv) != 3:
        print("Usage: python microservice.py <service_name> <port>")
        print("Examples:")
        print("  python microservice.py video 4434")
        print("  python microservice.py audio 4435")
        print("  python microservice.py chat 4436")
        print("  python microservice.py screen 4437")
        print("  python microservice.py file 4438")
        sys.exit(1)

    current_service_name = sys.argv[1] #Set global service name
    port = int(sys.argv[2])

    #Initialize config manager
    config_manager = MicroserviceConfigManager(MICROSERVICE_CONFIG_PATH)

    #Initial Pulsar setup based on loaded config
    await _reinitialize_pulsar_producer(
        config_manager.config.pulsar_broker_url,
        config_manager.config.send_to_pulsar,
        current_service_name
    )

    logger.info(f"🚀 Starting {current_service_name.upper()} Microservice on port {port}")
    logger.info(f"Pulsar sending is {'ENABLED' if SEND_TO_PULSAR else 'DISABLED'}.")

    #Create application
    app = create_app(current_service_name)

    #Start server
    runner = web.AppRunner(app)
    await runner.setup()

    #MODIFIED: Bind to '0.0.0.0' to listen on all interfaces
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    logger.info(f"✅ {current_service_name.upper()} Microservice is running on http://0.0.0.0:{port}")
    logger.info(f"📡 Endpoints:")
    logger.info(f"  POST /process_{current_service_name} - Process {current_service_name} data")
    logger.info(f"  GET /health - Health check")
    logger.info(f"⏹️  Press Ctrl+C to stop")

    #Keep running and check for config reloads
    try:
        while True:
            if config_manager.should_reload():
                logger.info("🔄 Microservice configuration changed, reloading...")
                config_manager.load_config()
                await _reinitialize_pulsar_producer(
                    config_manager.config.pulsar_broker_url,
                    config_manager.config.send_to_pulsar,
                    current_service_name
                )
            await asyncio.sleep(5) #Check for config changes every 5 seconds
    except KeyboardInterrupt:
        logger.info(f"🛑 {current_service_name.upper()} Microservice stopped")
    finally:
        await runner.cleanup()
        if producer:
            producer.close()
            logger.info("Pulsar producer closed.")
        if pulsar_client:
            pulsar_client.close()
            logger.info("Pulsar client closed.")

if __name__ == "__main__":
    asyncio.run(main())
