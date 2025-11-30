/**
 * Mock ClaudeCodeUI API Server
 *
 * Simulates the ClaudeCodeUI backend for ESP32 puck development.
 * Endpoints modeled after https://github.com/siteboon/claudecodeui
 */

const express = require('express');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());

const PORT = process.env.PORT || 3000;

// Simulated state - modify to test different scenarios
let mockState = {
  activeSessions: 2,
  projects: [
    {
      id: 'proj-001',
      name: 'homelab-infra',
      path: '/home/user/code/homelab',
      lastActive: new Date().toISOString(),
      git: {
        branch: 'feature/monitoring',
        status: 'dirty',
        changedFiles: 3,
        ahead: 1,
        behind: 0
      }
    },
    {
      id: 'proj-002',
      name: 'esp32-puck',
      path: '/home/user/code/esp32-puck',
      lastActive: new Date(Date.now() - 3600000).toISOString(),
      git: {
        branch: 'main',
        status: 'clean',
        changedFiles: 0,
        ahead: 0,
        behind: 0
      }
    }
  ],
  recentTasks: [
    {
      id: 'task-001',
      summary: 'Fixed auth bug in login.ts',
      status: 'completed',
      completedAt: new Date(Date.now() - 1800000).toISOString()
    },
    {
      id: 'task-002',
      summary: 'Added MetalLB static IP configuration',
      status: 'completed',
      completedAt: new Date(Date.now() - 7200000).toISOString()
    }
  ],
  runningAgents: []
};

// GET /api/status - Compact status for ESP32 (minimal payload)
app.get('/api/status', (req, res) => {
  const status = {
    sessions: mockState.activeSessions,
    agents: mockState.runningAgents.length,
    lastTask: mockState.recentTasks[0]?.summary?.substring(0, 40) || null,
    lastTaskTime: mockState.recentTasks[0]?.completedAt || null,
    gitDirty: mockState.projects.filter(p => p.git.status === 'dirty').length,
    timestamp: new Date().toISOString()
  };
  res.json(status);
});

// GET /api/projects - List all projects
app.get('/api/projects', (req, res) => {
  res.json(mockState.projects);
});

// GET /api/projects/:id - Single project details
app.get('/api/projects/:id', (req, res) => {
  const project = mockState.projects.find(p => p.id === req.params.id);
  if (!project) {
    return res.status(404).json({ error: 'Project not found' });
  }
  res.json(project);
});

// GET /api/tasks/recent - Recent tasks
app.get('/api/tasks/recent', (req, res) => {
  const limit = parseInt(req.query.limit) || 5;
  res.json(mockState.recentTasks.slice(0, limit));
});

// GET /api/agents - Running agents
app.get('/api/agents', (req, res) => {
  res.json(mockState.runningAgents);
});

// POST /api/mock/state - Update mock state for testing
app.post('/api/mock/state', (req, res) => {
  mockState = { ...mockState, ...req.body };
  console.log('Mock state updated:', JSON.stringify(mockState, null, 2));
  res.json({ success: true, state: mockState });
});

// POST /api/mock/scenario - Load predefined scenarios
app.post('/api/mock/scenario', (req, res) => {
  const { scenario } = req.body;

  const scenarios = {
    'idle': {
      activeSessions: 0,
      runningAgents: [],
      recentTasks: []
    },
    'busy': {
      activeSessions: 5,
      runningAgents: [
        { id: 'agent-1', type: 'code-reviewer', status: 'running' },
        { id: 'agent-2', type: 'test-runner', status: 'running' }
      ]
    },
    'error': {
      activeSessions: -1  // Signals error state
    }
  };

  if (scenarios[scenario]) {
    mockState = { ...mockState, ...scenarios[scenario] };
    res.json({ success: true, scenario, state: mockState });
  } else {
    res.status(400).json({ error: 'Unknown scenario', available: Object.keys(scenarios) });
  }
});

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'claude-code-api-mock' });
});

app.listen(PORT, () => {
  console.log(`Claude Code API Mock running on http://localhost:${PORT}`);
  console.log('Endpoints:');
  console.log('  GET  /api/status        - Compact status for ESP32');
  console.log('  GET  /api/projects      - List projects');
  console.log('  GET  /api/tasks/recent  - Recent tasks');
  console.log('  POST /api/mock/state    - Update mock state');
  console.log('  POST /api/mock/scenario - Load scenario (idle|busy|error)');
});
