#!/usr/bin/env python3
"""
Test usage scenarios of different embedding models
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv(project_root / ".env", override=True)

def test_embedding_selection():
    """Test embedding model selection under different configurations"""
    print("🧪 Test embedded model selection logic")
    print("=" * 60)
    
    from tradingagents.agents.utils.memory import FinancialSituationMemory
    from tradingagents.default_config import DEFAULT_CONFIG
    
    # test scenario 1: Ali Bailian
    print("📊 scene 1: Ali Bailian configuration")
    config1 = DEFAULT_CONFIG.copy()
    config1["llm_provider"] = "dashscope"
    config1["backend_url"] = "https://dashscope.aliyuncs.com/api/v1"
    
    try:
        memory1 = FinancialSituationMemory("test_dashscope", config1)
        print(f"✅ embedded model: {memory1.embedding}")
        print(f"   LLM provider: {memory1.llm_provider}")
        print(f"   client: {type(memory1.client)}")
    except Exception as e:
        print(f"❌ Alibaba Bailian configuration failed: {e}")
    
    print()
    
    # test scenario 2: local Ollama
    print("📊 scene 2: Local Ollama configuration")
    config2 = DEFAULT_CONFIG.copy()
    config2["llm_provider"] = "ollama"
    config2["backend_url"] = "http://localhost:11434/v1"
    
    try:
        memory2 = FinancialSituationMemory("test_ollama", config2)
        print(f"✅ embedded model: {memory2.embedding}")
        print(f"   LLM provider: {memory2.llm_provider}")
        print(f"   client: {type(memory2.client)}")
        print(f"   backend URL: {config2['backend_url']}")
    except Exception as e:
        print(f"❌ Local Ollama configuration failed: {e}")
    
    print()
    
    # test scenario 3: Google AI (problem scenario)
    print("📊 scene 3: Google AI Configuration (problem scenario)")
    config3 = DEFAULT_CONFIG.copy()
    config3["llm_provider"] = "google"
    config3["backend_url"] = "https://api.openai.com/v1"  # The default is still OpenAI URL
    
    try:
        memory3 = FinancialSituationMemory("test_google", config3)
        print(f"⚠️ embedded model: {memory3.embedding}")
        print(f"   LLM provider: {memory3.llm_provider}")
        print(f"   client: {type(memory3.client)}")
        print(f"   question: Google AI There is no special embedding configuration, the default is to use OpenAI")
    except Exception as e:
        print(f"❌ Google AI Configuration failed: {e}")
    
    print()
    
    # test scenario 4: OpenAI
    print("📊 scene 4: OpenAI Configuration")
    config4 = DEFAULT_CONFIG.copy()
    config4["llm_provider"] = "openai"
    config4["backend_url"] = "https://api.openai.com/v1"
    
    try:
        memory4 = FinancialSituationMemory("test_openai", config4)
        print(f"✅ embedded model: {memory4.embedding}")
        print(f"   LLM provider: {memory4.llm_provider}")
        print(f"   client: {type(memory4.client)}")
    except Exception as e:
        print(f"❌ OpenAI Configuration failed: {e}")

def test_embedding_functionality():
    """Test that embedding functionality is working properly"""
    print("\n🧪 Test embed functionality")
    print("=" * 60)
    
    from tradingagents.agents.utils.memory import FinancialSituationMemory
    from tradingagents.default_config import DEFAULT_CONFIG
    
    # Test Alibaba Bailian embedding
    dashscope_key = os.getenv('DASHSCOPE_API_KEY')
    if dashscope_key:
        print("📊 Test the Alibaba Bailian embedding function")
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "dashscope"
        
        try:
            memory = FinancialSituationMemory("test_embedding", config)
            embedding = memory.get_embedding("Apple stock analysis")
            print(f"✅ Alibaba Bailian embedded successfully")
            print(f"   embedded dimensions: {len(embedding)}")
            print(f"   Embed preview: {embedding[:5]}...")
        except Exception as e:
            print(f"❌ Alibaba Bailian embedding failed: {e}")
    else:
        print("⚠️ Alibaba Bailian API key is not configured and the test is skipped")
    
    print()
    
    # Test Google AI embedding (will fail)
    google_key = os.getenv('GOOGLE_API_KEY')
    if google_key:
        print("📊 Testing Google AI embed functionality (expected failure)")
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "google"
        
        try:
            memory = FinancialSituationMemory("test_google_embedding", config)
            embedding = memory.get_embedding("Apple stock analysis")
            print(f"✅ Google AI Embedding successful (unexpected)")
            print(f"   embedded dimensions: {len(embedding)}")
        except Exception as e:
            print(f"❌ Google AI Embedding failed (expected): {e}")
            print("   Reason: Google AI There is no dedicated embedding configuration, try using OpenAI API")
    else:
        print("⚠️ Google API Key not configured, test skipped")

def show_solutions():
    """Show solutions"""
    print("\n💡 solution")
    print("=" * 60)
    
    print("🔧 Plan 1: Add specialized embedding configuration for Google AI")
    print("   - Use Google s embedding API (if available)")
    print("   - Or use another compatible embedding service")
    
    print("\n🔧 Plan 2: Disable memory function")
    print("   - settings memory_enabled = False")
    print("   - Fix None check in code")
    
    print("\n🔧 Plan 3: Use Alibaba Bailian to embed")
    print("   - Even if LLM uses Google AI")
    print("   - Embedding still uses Alibaba Bailian")
    
    print("\n🔧 Plan 4: Use local embedding")
    print("   - Installation Ollama")
    print("   - Download the nomic-embed-text model")
    print("   - Runs entirely locally")
    
    print("\n📋 Comparison of various plans:")
    print("   Plan 1: Most ideal, but requires Google embed API")
    print("   Plan 2: The simplest, but loses memory function")
    print("   Plan 3: Practical, mix and match different services")
    print("   Plan 4: Best for privacy, but requires local resources")

def main():
    """Main test function"""
    print("🧪 Embedded model usage scenario analysis")
    print("=" * 70)
    
    test_embedding_selection()
    test_embedding_functionality()
    show_solutions()
    
    print(f"\n📊 Summary:")
    print("=" * 50)
    print("1. nomic-embed-text Is the embedding model used by local Ollama")
    print("2. Google AI There is no dedicated embedding configuration, the default attempt is to use OpenAI")
    print("3. This is why the memory feature is not available when testing Google AI")
    print("4. Need to add suitable embedding solution for Google AI")

if __name__ == "__main__":
    main()
