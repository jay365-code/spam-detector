import asyncio
import unittest
from unittest.mock import MagicMock, patch
import logging
import os

# Set dummy env vars
os.environ["LLM_PROVIDER"] = "GEMINI"
os.environ["GEMINI_API_KEY"] = "dummy_key"

# Mock key manager before importing nodes
with patch("app.agents.url_agent.nodes.key_manager") as mock_km:
    mock_km.get_key.return_value = "test_key"
    mock_km.rotate_key.return_value = True
    
    from app.agents.url_agent.nodes import analyze_node, analyze_with_vision

# Mock logger
logging.basicConfig(level=logging.INFO)

class TestURLAgenErrorHandling(unittest.IsolatedAsyncioTestCase):
    async def test_analyze_node_resource_exhausted(self):
        print("\nUsing mocked google.api_core.exceptions...")
        
        # Create a fake ResourceExhausted exception
        class FakeResourceExhausted(Exception):
            pass
            
        # We need to mock the import inside the function or just mock the exception type check
        # Since the function imports inside, we mock sys.modules or patch the module
        
        with patch("app.agents.url_agent.nodes.get_llm") as mock_get_llm, \
             patch("app.agents.url_agent.nodes.key_manager") as mock_key_manager, \
             patch("app.agents.url_agent.nodes.stop_after_attempt") as mock_stop, \
             patch("app.agents.url_agent.nodes.wait_exponential") as mock_wait:
             
            # Disable retries for speed
            mock_stop.return_value = lambda x: False # Don't stop? No, tenacity stop logic is complex to mock.
            # Instead, let's mock the retry decorator to just execute once or twice
            # Actually, we can just verify that the exception is caught and logic is triggered.
            
            # Setup LLM mock
            mock_llm_instance = MagicMock()
            mock_get_llm.return_value = mock_llm_instance
            
            # Setup exception
            # We need to simulate the exact behavior of checking google.api_core.exceptions
            # Since we can't easily import the real one if not installed, we can rely on string match too
            # The code checks for type OR string. "resource exhausted" string should trigger it.
            
            error_msg = "429 Resource has been exhausted (e.g. check quota)."
            mock_llm_instance.ainvoke.side_effect = Exception(error_msg)
            
            mock_key_manager.get_key.return_value = "current_key"
            mock_key_manager.rotate_key.return_value = True

            state = {
                "scraped_data": {"status": "success", "text": "test content", "url": "http://test.com"},
                "sms_content": "test sms"
            }
            
            # Run
            result = await analyze_node(state)
            
            # Verification
            # analyze_node catches exception and returns error dict
            # But inside specific inner function call_llm, it should log warning and call rotate_key
            
            print(f"Result: {result}")
            
            # Check if rotate_key was called
            # call_llm is decorated with retry. verification might be tricky if we don't mock retry.
            # But we can check if rotate_key was called at least once.
            
            # Note: analyze_node catches the final exception.
            # The retry logic inside analyze_node will retry 3 times.
            # On generic Exception, it checks string "resource exhausted".
            
            self.assertTrue(mock_key_manager.rotate_key.called)
            print("Verified: rotate_key was called.")
            
    async def test_analyze_with_vision_resource_exhausted(self):
        print("\nTesting analyze_with_vision error handling...")
         # Create a fake ResourceExhausted exception
        class FakeResourceExhausted(Exception):
             pass

        with patch("app.agents.url_agent.nodes.key_manager") as mock_key_manager, \
             patch("google.generativeai.GenerativeModel") as mock_gen_model_cls:
             
             mock_model = MagicMock()
             mock_gen_model_cls.return_value = mock_model
             
             # Mock generate_content to raise exception
             mock_model.generate_content.side_effect = Exception("429 Resource exhausted")
             
             mock_key_manager.get_key.return_value = "gemini_key"
             mock_key_manager.rotate_key.return_value = True
             
             # Need to patch asyncio.get_running_loop to run sync function
             # The code uses run_in_executor
             
             await analyze_with_vision("base64data", "http://test.com", "Title")
             
             self.assertTrue(mock_key_manager.rotate_key.called)
             print("Verified: rotate_key was called for vision.")

if __name__ == "__main__":
    unittest.main()
