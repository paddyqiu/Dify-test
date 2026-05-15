# Dify-Test

LINE Bot + Neo4j + Dify + Flask knowledge graph query system.

This project integrates:

* LINE Messaging API
* Dify AI Workflow
* Neo4j Knowledge Graph
* Flask API
* Render Deployment

The bot supports:

* Knowledge graph node query
* Relationship query
* Graph image generation
* Duplicate node selection
* Group mention reply mode
* Neo4j relationship visualization

---

# System Architecture

```text
LINE
↓
Flask Webhook
↓
line_flow_service.py
↓
Dify AI Workflow
↓
Neo4j Query API
↓
Graph Result
↓
Graph Image Generator
↓
LINE Response
```

---

# Project Structure

```text
project/
│
├── app.py
├── config.py
│
├── fonts/
│   └── NotoSansCJKtc-Regular.otf
│
├── service/
│   ├── dify_service.py
│   ├── graph_service.py
│   ├── graph_image_service.py
│   ├── graph_web_service.py
│   ├── line_flow_service.py
│   └── line_service.py
│
├── data/
│   ├── relation_data.json
│   └── node_schema.json
│
├── requirements.txt
└── README.md
```

---

# Main Features

## 1. Node Query

Example:

```text
BHC212
```

Returns:

* Node properties
* Related nodes
* Graph image

---

## 2. Relationship Query

Example:

```text
BHC212跟ACP212有甚麼關聯
```

Returns:

* Neo4j relationship result
* Relationship graph image

---

## 3. Graph Image Generation

Supports:

* Single node graph
* Two-node relationship graph

Generated using:

* matplotlib
* networkx

---

## 4. Duplicate Node Selection

If multiple nodes share the same name:

```text
目前找到多個名稱為 XXX 的節點
```

The system allows user selection.

---

# Environment Variables (Render)

All environment variables are managed in Render Environment Variables.

Required:

```text
PUBLIC_BASE_URL
LINE_CHANNEL_ACCESS_TOKEN
LINE_CHANNEL_SECRET
DIFY_API_KEY
DIFY_BASE_URL
NEO4J_URI
NEO4J_USER
NEO4J_PASSWORD
```

Example:

```text
PUBLIC_BASE_URL=https://your-service.onrender.com
```

---

# Render Deployment

## Start Command

```text
gunicorn app:app
```

---

# LINE Webhook

Webhook URL:

```text
https://your-service.onrender.com/line/webhook
```

---

# Graph APIs

## Single Node Graph

```text
/graph/image?target=BHC212
```

---

## Relationship Graph

```text
/graph/relation-image?source=BHC212&relation=INCLUDES&target=ACP212
```

---

# Dependencies

Main libraries:

```text
Flask
gunicorn
requests
neo4j
matplotlib
networkx
line-bot-sdk
```

Install:

```bash
pip install -r requirements.txt
```

---

# Current Features

* Neo4j node query
* Relationship query
* Graph image generation
* LINE group mention mode
* Dify AI integration
* Duplicate node selection
* Dynamic graph visualization

---

# Future Improvements

* Multi-hop graph visualization
* Subgraph expansion
* Better graph layout
* Caching optimization
* Full graph exploration mode
* Graph interaction UI

---

# Notes

* Environment variables are NOT stored in GitHub.
* All secrets are managed through Render Environment Variables.
* The system uses Dify as the LLM orchestration layer.
* Neo4j Aura is used as the graph database backend.

---
