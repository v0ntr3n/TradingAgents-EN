# Web Interface screenshot directory

This directory is used to store screenshot files of the TradingAgents-CN web interface.

## 📸 Required screenshot files

In order to improve the web interface display in README.md, please add the following screenshot:

### 🏠 Screenshot of main interface
- **file name**: `web-interface-main.png`
- **content**: Main analysis configuration interface
- **request**: 
  - Show stock code input box
  - Display market selection (US stocks/A shares/Hong Kong stocks)
  - Display research depth selection (level 1-5)
  - Show agent selection options
  - show"Start analysis"button

### 📊 Real-time analysis progress screenshots
- **file name**: `web-interface-progress.png`
- **content**: Progress display of analysis in progress
- **request**:
  - Show progress bar and percentage
  - Show current analysis step
  - Show estimated remaining time
  - Show completed analysis stages

### 📈 Screenshot of analysis results display
- **file name**: `web-interface-results.png`
- **content**: Complete analysis results page
- **request**:
  - Shows the tendency of research conclusions (optimistic/cautious/neutral)
  - Show confidence and risk scores
  - Show detailed analysis report
  - Show export button

### ⚙️ Screenshot of model configuration management
- **file name**: `web-interface-models.png`
- **content**: Model configuration interface in the sidebar
- **request**:
  - Show LLM provider selections
  - Show model selection drop-down box
  - Show quick select button
  - Show API key configuration status

## 📋 Screenshot specifications

### 🖼️ Technical requirements
- **Format**: PNG Format (recommended)
- **resolution**: at least 1920x1080
- **quality**: HD, text is clear and readable
- **size**: A single file does not exceed 2MB

### 🎨 Content requirements
- **Complete interface**: Show full functional area
- **Data is real**: Use real stock symbols and analysis results
- **clear status**: Ensure interface status is clearly visible
- **No sensitive information**: Does not contain real API key

### 📱 Suggested screenshot scenarios
1. **Main interface**: input"AAPL"or"000001", Selection criteria analysis
2. **Progress interface**: The analysis reaches about 50% state
3. **Result interface**: Full analysis report including charts and graphs
4. **Configuration interface**: Display multiple LLM providers and model options

## 🚀 How to get screenshots

### method 1: Start web application
```bash
# Start the web interface
python start_web.py

# visit http://localhost:8501
# Conduct stock analysis and take screenshots
```

### method 2: Docker environment
```bash
# Start the Docker service
docker-compose up -d

# visit http://localhost:8501
# Analyze and take screenshots
```

## 📝 What to do after adding a screenshot

1. Place the screenshot file into this directory
2. Make sure the file name matches the name referenced in README.md
3. Check whether the picture is displayed normally
4. Submit to Git repository

## 🔄 Update instructions

When there are major updates to the web interface, please update the corresponding screenshots in a timely manner to ensure that the document is consistent with the actual interface.

---

**Note**: The screenshots in this directory will be displayed in README.md to represent the professional image of the project. Please ensure the quality of the screenshots and the professionalism of the content.
