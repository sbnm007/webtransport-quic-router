# WebTransport Pulsar Streaming Platform

A high-performance real-time streaming platform that combines WebTransport protocol with Apache Pulsar messaging system for ultra-low latency multimedia streaming.

## 🚀 Features

- **WebTransport Protocol**: Leverages HTTP/3 and QUIC for ultra-low latency streaming
- **Apache Pulsar Integration**: Distributed messaging system for scalable message routing
- **Real-time Video/Audio**: Live media streaming with configurable quality settings
- **Live Chat**: Instant messaging with WebTransport streams
- **Microservices Architecture**: Containerized router and microservice components
- **Performance Metrics**: Comprehensive latency and throughput monitoring
- **Docker Support**: Easy deployment with Docker Compose

## 📋 Prerequisites

- Python 3.8+
- Docker & Docker Compose
- Modern web browser with WebTransport support (Chrome 97+, Edge 97+)
- Apache Pulsar cluster (local or remote)

## 🛠️ Installation & Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd wt_pulsar
```

### 2. Set up Python Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install pulsar-client pyyaml asyncio websockets
```

**Note**: For local development, always activate the virtual environment before running any Python scripts.

### 3. Start Apache Pulsar

```bash
#Local Pulsar setup (if needed)
docker-compose -f local/docker-compose.yml up -d
```

### 4. Configure Services

Update the configuration files:
- `router/router_config.yaml` - Router configuration
- `microservice/microservice.yaml` - Microservice configuration
- `local/microservice_config.yaml` - Local development config

### 5. Configure Client Hostname

Update the WebTransport client hostname in `live_client.html`:

**For Local Development:**
```javascript
//Configuration
this.serverUrl = 'https://localhost:4433/wt';  // Local development
//this.serverUrl = 'https://quic-aioquic.com/wt';  // Production/Remote
```

**For Kubernetes Deployment:**
```javascript
//Configuration
this.serverUrl = 'https://your-k8s-ingress-hostname/wt';  // Kubernetes
//this.serverUrl = 'https://quic-aioquic.com/wt';  // Production/Remote
```

**For Production/Remote:**
```javascript
//Configuration
//this.serverUrl = 'https://localhost:4433/wt';  // Local development
this.serverUrl = 'https://quic-aioquic.com/wt';  // Production/Remote
```

## 🏃‍♂️ Running the Application

### Option 1: Docker Deployment

```bash
#Start all services
docker-compose up -d

#Check service status
docker-compose ps
```

### Option 2: Local Development

**Prerequisites:**
- Activate virtual environment: `source venv/bin/activate`
- Ensure Pulsar is running locally or accessible remotely

```bash
#Terminal 1: Start Router
cd router
python router.py

#Terminal 2: Start Microservice
cd microservice
python microservice.py video

#Terminal 3: Start Consumer
python consumer.py video
```

### Option 3: Local Testing (Simplified)

**Prerequisites:**
- Activate virtual environment: `source venv/bin/activate`
- Update hostname in `live_client.html` for local development

```bash
#Start local services
cd local
python router.py &
python microservice.py video &

#Open web client (update serverUrl to localhost:4433)
open live_client.html
```

## 📁 Project Structure

```
wt_pulsar/
├── consumer.py              # Pulsar message consumer
├── live_client.html         # WebTransport client interface
├── router/                  # Router microservice
│   ├── router.py           
│   ├── Dockerfile
│   ├── router_config.yaml
│   └── requirements.txt
├── microservice/           # Processing microservice
│   ├── microservice.py
│   ├── Dockerfile
│   ├── microservice.yaml
│   └── requirements.txt
├── local/                  # Local development
│   ├── router.py
│   ├── microservice.py
│   ├── docker-compose.yml
│   └── microservice_config.yaml
├── data/                   # Pulsar data (auto-generated)
├── final-cert/            # SSL certificates for WebTransport
└── README.md
```

## 🔧 Configuration

### Router Configuration (`router_config.yaml`)

```yaml
services:
  video:
    url: "http://microservice:8080/process"
    data_format: "binary"
  audio:
    url: "http://microservice:8080/process"
    data_format: "binary"
  chat:
    url: "http://microservice:8080/process"
    data_format: "json"

global:
  max_retries: 3
  timeout: 5.0
```

### Microservice Configuration (`microservice.yaml`)

```yaml
pulsar:
  broker_url: "pulsar://pulsar:6650"
  send_to_pulsar: true

logging:
  level: "INFO"
```

## 🚀 Usage

### 1. WebTransport Client

**Important**: Update the server hostname in `live_client.html` based on your deployment:

1. Open `live_client.html` in a modern browser
2. Ensure the `serverUrl` matches your deployment environment:
   - Local: `https://localhost:4433/wt`
   - Kubernetes: `https://your-k8s-hostname/wt`
   - Production: `https://quic-aioquic.com/wt`
3. Click "Start Streaming" to begin video/audio capture
4. Use the chat interface for real-time messaging
5. Monitor performance metrics in real-time

### 2. Pulsar Consumer

**Prerequisites**: Activate virtual environment before running consumers

```bash
#Activate venv
source venv/bin/activate

#Start consumer for specific topic
python consumer.py video

#Consumer supports various topics: video, audio, chat, screen, file
python consumer.py chat
```

### 3. API Endpoints

- **Router**: `https://quic-aioquic.com/wt` (WebTransport)
- **Microservice**: `http://localhost:8080/process` (HTTP)
- **Health Check**: `http://localhost:8080/health`

## 📊 Performance Metrics

The platform tracks comprehensive metrics:

- **End-to-End Latency**: Target <10ms for real-time applications
- **Video Frame Rate**: 15-30 FPS (configurable)
- **Audio Sample Rate**: 44.1kHz with noise suppression
- **Throughput**: Real-time data rate monitoring
- **Buffer Metrics**: Queue depth and processing times

### Metrics Files

- `router/metrics/buffer_metrics_*.csv` - Performance data
- `router/metrics/buffer_events_*.log` - Event logs

## 🐳 Docker Deployment

### Building Images

**Build Router Image:**
```bash
cd router
docker build -t wt-router:latest .
```

**Build Microservice Image:**
```bash
cd microservice
docker build -t wt-microservice:latest .
```

**Build All Images:**
```bash
#Build all services using docker-compose
docker-compose build

#Build with specific tags
docker-compose build --build-arg VERSION=1.0.0
```

### Single Service Deployment

```bash
#Build and run router
cd router
docker build -t wt-router .
docker run -p 443:443 -p 4433:4433 wt-router

#Build and run microservice
cd microservice
docker build -t wt-microservice .
docker run -p 8080:8080 wt-microservice
```

### Full Stack Deployment

```bash
#Deploy all services
docker-compose up -d

#Scale microservices
docker-compose up -d --scale microservice=3

#View logs
docker-compose logs -f router
```

### Kubernetes Deployment

**Prerequisites:**
- Update `live_client.html` with Kubernetes ingress hostname
- Configure ingress controller for WebTransport support
- Ensure TLS certificates are properly configured

```bash
#Apply Kubernetes manifests
kubectl apply -f k8s/

#Check deployment status
kubectl get pods -l app=wt-pulsar

#Access via ingress
kubectl get ingress wt-pulsar-ingress
```

## 🔒 Security

- **TLS/SSL**: WebTransport requires HTTPS with valid certificates
- **CORS**: Configured for cross-origin requests
- **Authentication**: Implement token-based auth for production

## 🧪 Testing

### Load Testing

**Prerequisites**: Activate virtual environment and ensure proper hostname configuration

```bash
#Activate venv
source venv/bin/activate

#Multiple consumers for load testing
python consumer.py video &
python consumer.py audio &
python consumer.py chat &
```

### Client Configuration Testing

Test different deployment scenarios by updating `live_client.html`:

```bash
#Test local deployment
sed -i "s|this.serverUrl = '.*';|this.serverUrl = 'https://localhost:4433/wt';|" live_client.html

#Test Kubernetes deployment  
sed -i "s|this.serverUrl = '.*';|this.serverUrl = 'https://your-k8s-hostname/wt';|" live_client.html

#Test production deployment
sed -i "s|this.serverUrl = '.*';|this.serverUrl = 'https://quic-aioquic.com/wt';|" live_client.html
```

### Performance Testing

1. Monitor `buffer_metrics_*.csv` for performance data
2. Check end-to-end latency in consumer output
3. Use browser DevTools for WebTransport debugging

## 🐛 Troubleshooting

### Common Issues

1. **WebTransport Connection Failed**
   - Ensure valid SSL certificates
   - Check browser WebTransport support
   - Verify server URL and port

2. **Pulsar Connection Issues**
   - Confirm Pulsar broker is running
   - Check broker URL in configuration
   - Verify network connectivity

3. **Media Capture Errors**
   - Grant browser camera/microphone permissions
   - Check device availability
   - Verify HTTPS context

4. **Wrong Hostname Configuration**
   - Update `serverUrl` in `live_client.html` for your environment
   - Local: `https://localhost:4433/wt`
   - Kubernetes: `https://your-k8s-hostname/wt`
   - Ensure hostname matches your deployment

5. **Virtual Environment Issues**
   - Always activate venv: `source venv/bin/activate`
   - Install dependencies: `pip install pulsar-client pyyaml`
   - Check Python path: `which python`

### Debug Commands

```bash
#Check Pulsar topics
docker exec -it pulsar bin/pulsar-admin topics list public/default

#Monitor Docker containers
docker-compose logs -f

#Test WebTransport endpoint
curl -k https://quic-aioquic.com/health
```

## 📈 Performance Optimization

- **Video Quality**: Adjust resolution and frame rate based on bandwidth
- **Audio Compression**: Use appropriate bit rates for quality vs. size
- **Buffer Tuning**: Configure receiver queue sizes for optimal performance
- **Network**: Ensure low-latency network path for best results

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Apache Pulsar team for the messaging platform
- WebTransport specification contributors
- QUIC protocol developers

## 📞 Support

For issues and questions:
- Create an issue in the GitHub repository
- Check the troubleshooting section
- Review performance metrics for debugging

---

**Built with ❤️ for high-performance real-time streaming**
