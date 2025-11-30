/**
 * Mock Home Assistant REST API Server
 *
 * Simulates Home Assistant REST API endpoints for ESP32 puck development.
 * Based on: https://developers.home-assistant.io/docs/api/rest/
 */

const express = require('express');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());

const PORT = process.env.PORT || 8123;
const VALID_TOKEN = 'mock-ha-token-12345';

// Middleware to validate Bearer token
const authenticate = (req, res, next) => {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ message: 'Missing or invalid authorization header' });
  }
  const token = authHeader.substring(7);
  if (token !== VALID_TOKEN && token !== process.env.HA_TOKEN) {
    return res.status(401).json({ message: 'Invalid access token' });
  }
  next();
};

// Simulated entity states
let entities = {
  'sensor.server_cpu_temp': {
    entity_id: 'sensor.server_cpu_temp',
    state: '65',
    attributes: {
      unit_of_measurement: '°C',
      friendly_name: 'Server CPU Temperature',
      device_class: 'temperature'
    },
    last_changed: new Date().toISOString()
  },
  'sensor.server_memory_used': {
    entity_id: 'sensor.server_memory_used',
    state: '72',
    attributes: {
      unit_of_measurement: '%',
      friendly_name: 'Server Memory Usage'
    },
    last_changed: new Date().toISOString()
  },
  'switch.office_lights': {
    entity_id: 'switch.office_lights',
    state: 'off',
    attributes: {
      friendly_name: 'Office Lights',
      icon: 'mdi:lightbulb'
    },
    last_changed: new Date().toISOString()
  },
  'binary_sensor.k8s_cluster_healthy': {
    entity_id: 'binary_sensor.k8s_cluster_healthy',
    state: 'on',
    attributes: {
      friendly_name: 'K8s Cluster Health',
      device_class: 'connectivity'
    },
    last_changed: new Date().toISOString()
  },
  'sensor.active_alerts': {
    entity_id: 'sensor.active_alerts',
    state: '0',
    attributes: {
      friendly_name: 'Active Alerts',
      icon: 'mdi:alert'
    },
    last_changed: new Date().toISOString()
  }
};

let notifications = [
  { id: 1, title: 'Backup completed', message: 'Daily backup finished successfully' },
  { id: 2, title: 'Update available', message: 'Home Assistant 2024.1 is available' },
  { id: 3, title: 'Low disk space', message: 'NAS storage below 10%' }
];

// GET /api/ - API status
app.get('/api/', authenticate, (req, res) => {
  res.json({ message: 'API running.' });
});

// GET /api/states - All entity states
app.get('/api/states', authenticate, (req, res) => {
  res.json(Object.values(entities));
});

// GET /api/states/:entity_id - Single entity state
app.get('/api/states/:entity_id', authenticate, (req, res) => {
  const entity = entities[req.params.entity_id];
  if (!entity) {
    return res.status(404).json({ message: 'Entity not found' });
  }
  res.json(entity);
});

// POST /api/services/:domain/:service - Call a service
app.post('/api/services/:domain/:service', authenticate, (req, res) => {
  const { domain, service } = req.params;
  const { entity_id } = req.body;

  console.log(`Service call: ${domain}.${service} on ${entity_id}`);

  // Simulate toggle for switches
  if (domain === 'switch' && service === 'toggle' && entities[entity_id]) {
    entities[entity_id].state = entities[entity_id].state === 'on' ? 'off' : 'on';
    entities[entity_id].last_changed = new Date().toISOString();
  }

  // Simulate turn_on/turn_off
  if (service === 'turn_on' && entities[entity_id]) {
    entities[entity_id].state = 'on';
    entities[entity_id].last_changed = new Date().toISOString();
  }
  if (service === 'turn_off' && entities[entity_id]) {
    entities[entity_id].state = 'off';
    entities[entity_id].last_changed = new Date().toISOString();
  }

  res.json([entities[entity_id] || { success: true }]);
});

// GET /api/config - HA configuration
app.get('/api/config', authenticate, (req, res) => {
  res.json({
    location_name: 'Homelab',
    version: '2024.1.0',
    unit_system: { temperature: '°C' }
  });
});

// Custom endpoint for ESP32: compact status
app.get('/api/puck/status', authenticate, (req, res) => {
  // Return only what the ESP32 needs
  const status = {
    cpu_temp: parseInt(entities['sensor.server_cpu_temp'].state),
    memory_pct: parseInt(entities['sensor.server_memory_used'].state),
    k8s_healthy: entities['binary_sensor.k8s_cluster_healthy'].state === 'on',
    alerts: parseInt(entities['sensor.active_alerts'].state),
    notifications: notifications.length,
    office_lights: entities['switch.office_lights'].state === 'on',
    timestamp: new Date().toISOString()
  };
  res.json(status);
});

// POST /api/mock/entity - Update entity for testing
app.post('/api/mock/entity', (req, res) => {
  const { entity_id, state, attributes } = req.body;
  if (entities[entity_id]) {
    entities[entity_id].state = String(state);
    if (attributes) {
      entities[entity_id].attributes = { ...entities[entity_id].attributes, ...attributes };
    }
    entities[entity_id].last_changed = new Date().toISOString();
    res.json({ success: true, entity: entities[entity_id] });
  } else {
    // Create new entity
    entities[entity_id] = {
      entity_id,
      state: String(state),
      attributes: attributes || {},
      last_changed: new Date().toISOString()
    };
    res.json({ success: true, entity: entities[entity_id] });
  }
});

// POST /api/mock/scenario - Load predefined scenarios
app.post('/api/mock/scenario', (req, res) => {
  const { scenario } = req.body;

  const scenarios = {
    'all-good': () => {
      entities['sensor.server_cpu_temp'].state = '45';
      entities['sensor.active_alerts'].state = '0';
      entities['binary_sensor.k8s_cluster_healthy'].state = 'on';
      notifications = [];
    },
    'high-temp': () => {
      entities['sensor.server_cpu_temp'].state = '85';
      entities['sensor.active_alerts'].state = '1';
    },
    'cluster-down': () => {
      entities['binary_sensor.k8s_cluster_healthy'].state = 'off';
      entities['sensor.active_alerts'].state = '3';
    },
    'auth-expired': () => {
      // This scenario is handled differently - see route
    }
  };

  if (scenarios[scenario]) {
    scenarios[scenario]();
    res.json({ success: true, scenario });
  } else {
    res.status(400).json({ error: 'Unknown scenario', available: Object.keys(scenarios) });
  }
});

// Health check (no auth required)
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'home-assistant-api-mock' });
});

app.listen(PORT, () => {
  console.log(`Home Assistant API Mock running on http://localhost:${PORT}`);
  console.log(`Valid token: ${VALID_TOKEN}`);
  console.log('Endpoints:');
  console.log('  GET  /api/states           - All entities');
  console.log('  GET  /api/states/:id       - Single entity');
  console.log('  POST /api/services/:d/:s   - Call service');
  console.log('  GET  /api/puck/status      - Compact status for ESP32');
  console.log('  POST /api/mock/entity      - Update entity');
  console.log('  POST /api/mock/scenario    - Load scenario');
});
