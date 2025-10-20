#!/usr/bin/env python3
"""
Test script for advisor mode functionality.
Tests mode switching and advisor responses.
"""

import requests
import json

BASE_URL = "http://localhost:8000"
SESSION_ID = "test-advisor-demo"

def test_mode_switch():
    """Test switching to advisor mode."""
    print("=" * 80)
    print("TEST 1: Switching to Advisor Mode")
    print("=" * 80)
    
    response = requests.post(
        f"{BASE_URL}/api/switch_mode",
        json={"sessionId": SESSION_ID, "mode": "advisor"}
    )
    
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Mode: {data.get('mode')}")
    print(f"Reply: {data.get('reply')[:200]}...")
    print()
    
    return response.status_code == 200


def test_advisor_question(question):
    """Test asking a question in advisor mode."""
    print("=" * 80)
    print(f"TEST: Advisor Question - {question}")
    print("=" * 80)
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={"sessionId": SESSION_ID, "message": question}
    )
    
    data = response.json()
    
    print(f"Status: {response.status_code}")
    print(f"Mode: {data.get('mode', 'Not specified')}")
    print(f"\nResponse:\n{data.get('reply')[:500]}...")
    
    if 'sources' in data and data['sources']:
        print(f"\nSources consulted: {', '.join(data['sources'])}")
    
    if 'suggested_questions' in data and data['suggested_questions']:
        print(f"\nSuggested follow-ups:")
        for i, q in enumerate(data['suggested_questions'], 1):
            print(f"  {i}. {q}")
    
    print()
    return response.status_code == 200


def test_broker_mode():
    """Test switching back to broker mode."""
    print("=" * 80)
    print("TEST: Switching back to Broker Mode")
    print("=" * 80)
    
    response = requests.post(
        f"{BASE_URL}/api/switch_mode",
        json={"sessionId": SESSION_ID, "mode": "broker"}
    )
    
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Mode: {data.get('mode')}")
    print(f"Reply: {data.get('reply')[:200]}...")
    print()
    
    return response.status_code == 200


if __name__ == "__main__":
    print("\n🎓 ADVISOR MODE TEST SUITE 🎓\n")
    
    # Test 1: Switch to advisor mode
    success = test_mode_switch()
    if not success:
        print("❌ Failed to switch to advisor mode")
        exit(1)
    
    # Test 2: Ask advisor questions
    questions = [
        "How do I register for Bostad Uppsala?",
        "What are queue days?",
        "Which neighborhoods in Uppsala are cheapest?",
    ]
    
    for question in questions:
        success = test_advisor_question(question)
        if not success:
            print(f"❌ Failed on question: {question}")
            exit(1)
    
    # Test 3: Switch back to broker mode
    success = test_broker_mode()
    if not success:
        print("❌ Failed to switch back to broker mode")
        exit(1)
    
    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED!")
    print("=" * 80)
    print("\nAdvisor mode is fully functional! 🎉")
    print("\nNext steps:")
    print("1. Add mode toggle UI in frontend (static/index.html)")
    print("2. Style advisor responses differently")
    print("3. Display suggested follow-up questions")
    print("4. Show source citations in UI")
