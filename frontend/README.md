# TradingAgents-CN Frontend Application

A modern Vue 3 frontend interface providing a smooth user experience for TradingAgents-CN.

## 🚀 Quick Start

### Prerequisites

- Node.js >= 18.0.0
- npm >= 8.0.0

### Install Dependencies

```bash
npm install
```

### Start Development Server

```bash
npm run dev
```

Visit http://localhost:3000

### Build for Production

```bash
npm run build
```

### Preview Production Build

```bash
npm run preview
```

## 📁 Project Structure

```
frontend/
├── public/                 # Static assets
├── src/
│   ├── api/               # API interfaces
│   ├── components/        # Components
│   │   ├── Global/       # Global components
│   │   └── Layout/       # Layout components
│   ├── layouts/          # Page layouts
│   ├── router/           # Router configuration
│   ├── stores/           # State management
│   ├── styles/           # Stylesheets
│   ├── types/            # Type definitions
│   ├── utils/            # Utility functions
│   ├── views/            # View components
│   ├── App.vue           # Root component
│   └── main.ts           # Application entry point
├── index.html            # HTML template
├── package.json          # Project configuration
├── tsconfig.json         # TypeScript configuration
├── vite.config.ts        # Vite configuration
└── README.md             # Documentation
```

## 🎨 Key Features

### 📊 Dashboard
- Data overview and statistics
- Quick action entry points
- System status monitoring
- Recent analysis records

### 🔍 Stock Screening
- Multi-dimensional filtering criteria
- Real-time results display
- Batch operation support
- Screening results export

### 📈 Stock Analysis
- Single-stock deep analysis
- Batch analysis processing
- Analysis history viewing
- Real-time progress tracking

### 📋 Queue Management
- Task queue monitoring
- Real-time status updates
- Task priority management
- Batch operation support

### 📄 Analysis Reports
- Report generation and management
- Multi-format export support
- Report sharing functionality
- Historical report viewing

### ⚙️ System Settings
- Personal preference configuration
- Theme and appearance settings
- Analysis parameter configuration
- Security settings management

## 🛠️ Tech Stack

### Core Framework
- **Vue 3** - Progressive JavaScript framework
- **TypeScript** - Type-safe JavaScript
- **Vite** - Next-generation frontend build tool

### UI Component Library
- **Element Plus** - Enterprise-grade Vue 3 UI component library
- **@element-plus/icons-vue** - Icon components

### State Management
- **Pinia** - Official Vue state management library
- **@vueuse/core** - Collection of Vue Composition API utilities

### Routing & Networking
- **Vue Router 4** - Official router for Vue.js
- **Axios** - Promise-based HTTP client

### Development Tools
- **ESLint** - Code quality linting
- **Prettier** - Code formatting
- **unplugin-auto-import** - Auto-importing APIs
- **unplugin-vue-components** - On-demand component auto-importing

## 🎯 Highlights

### 🌈 Modern Design
- Responsive layout design
- Light and dark theme switching
- Smooth animations and transitions
- Mobile device adaptation

### 🔧 Developer Experience
- TypeScript type safety
- Automatic component importing
- Hot Module Replacement (HMR)
- Code splitting optimization

### 🚀 Performance Optimization
- Route lazy loading
- On-demand component loading
- Image lazy loading
- Caching strategy optimization

### 🔒 Security Features
- JWT authentication integration
- Permission navigation guards
- XSS protection
- CSRF protection

## 📱 Responsive Design

Supports multiple device screen sizes:

- **Desktop**: >= 1200px
- **Tablet**: 768px - 1199px  
- **Mobile**: < 768px

## 🎨 Theme Customization

Supports multiple theme modes:

- **Light Theme**: Suitable for daytime use
- **Dark Theme**: Suitable for nighttime use
- **Auto Mode**: Follows system preferences

## 🔧 Configuration

### Environment Variables

Create a `.env.local` file:

```env
# API Base URL
VITE_API_BASE_URL=http://localhost:8000/api

# Application Title
VITE_APP_TITLE=TradingAgents-CN
```

### Proxy Configuration

The development environment automatically proxies API requests to the backend service:

```typescript
// vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true
    }
  }
}
```

## 🚀 Deployment Guide

### Build Application

```bash
npm run build
```

### Deploy with Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;
    root /path/to/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 🤝 Development Guide

### Adding a New Page

1. Create a view component in `src/views/`
2. Add the route in `src/router/index.ts`
3. Add a navigation entry in the sidebar menu

### Adding a New API

1. Define types in `src/types/`
2. Create an API module in `src/api/`
3. Call the API in your component

### State Management

Use Pinia for state management:

```typescript
// Define a store
export const useExampleStore = defineStore('example', {
  state: () => ({
    data: []
  }),
  actions: {
    async fetchData() {
      // Data fetching logic
    }
  }
})

// Use in a component
const exampleStore = useExampleStore()
```

## 📝 Coding Standards

### Naming Conventions
- Component names: PascalCase
- File names: kebab-case
- Variable names: camelCase
- Constant names: UPPER_SNAKE_CASE

### Commit Conventions
- feat: New feature
- fix: Bug fix
- docs: Documentation update
- style: Code formatting changes
- refactor: Code refactoring
- test: Test-related changes
- chore: Build process or auxiliary tool changes

## 🐛 Troubleshooting

### Common Issues

1. **Dependency installation failed**
   ```bash
   rm -rf node_modules package-lock.json
   npm install
   ```

2. **Port already in use**
   ```bash
   # Specify a different port
   npm run dev -- --port 3001
   ```

3. **Type errors**
   ```bash
   # Run type checking
   npm run type-check
   ```

## 📞 Technical Support

If you have any questions, please reach out via:

- 📧 Email: hsliup@163.com
- 💬 WeChat Group: Scan the QR code in the README
- 🐛 Issue Tracker: GitHub Issues

---

**TradingAgents-CN Frontend v3.0.0** - A modern frontend for AI assistants and intelligent investment research workflows
