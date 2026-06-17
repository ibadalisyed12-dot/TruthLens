import os
import json
import re
import logging
import requests
import search
import classifier

logger = logging.getLogger(__name__)

def extract_json_from_text(text: str) -> dict | None:
    """
    Attempts to extract and parse a JSON object from text that might contain markdown blocks.
    """
    if not text:
        return None
        
    cleaned = text.strip()
    
    # Remove markdown code blocks if present
    if cleaned.startswith("```"):
        # Matches ```json <content> ``` or ``` <content> ```
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()
            
    try:
        return json.loads(cleaned)
    except Exception as e:
        logger.warning(f"JSON direct parsing failed: {e}. Trying simple regex matching...")
        
    # Fallback: find first '{' and last '}'
    try:
        start_idx = cleaned.find('{')
        end_idx = cleaned.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = cleaned[start_idx:end_idx + 1]
            return json.loads(json_str)
    except Exception as regex_err:
        logger.error(f"Regex JSON extraction failed: {regex_err}")
        
    return None

def run_gemini_reasoning(prompt: str, api_key: str) -> dict | None:
    """
    Sends the reasoning prompt to Google Gemini API.
    """
    logger.info("Running reasoning audit via Google Gemini API...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=12)
        if response.status_code == 200:
            resp_json = response.json()
            candidates = resp_json.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    text_out = parts[0].get("text", "").strip()
                    parsed_json = extract_json_from_text(text_out)
                    if parsed_json:
                        return parsed_json
        else:
            logger.warning(f"Gemini API returned status code {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Gemini API request failed: {e}")
    return None

def run_anthropic_reasoning(prompt: str, api_key: str) -> dict | None:
    """
    Sends the reasoning prompt to Anthropic Claude API.
    """
    logger.info("Running reasoning audit via Anthropic Claude API...")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    data = {
        "model": "claude-3-5-sonnet-latest",
        "max_tokens": 1000,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        response = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=data, timeout=12)
        if response.status_code == 200:
            resp_json = response.json()
            content = resp_json.get("content", [])
            if content:
                text_out = content[0].get("text", "").strip()
                parsed_json = extract_json_from_text(text_out)
                if parsed_json:
                    return parsed_json
        else:
            logger.warning(f"Anthropic API returned status code {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Anthropic API request failed: {e}")
    return None

def run_fallback_local_reasoning(claim_text: str, search_results: list[dict]) -> dict:
    """
    Simulates a search reasoning audit locally using classifier models and search content.
    Used when no LLM API keys are configured.
    """
    logger.info("No LLM API keys configured. Running local fallback reasoning mode...")
    
    # 1. Run local classifier
    class_res = classifier.classify_text(claim_text)
    fake_prob = class_res["fake_probability"]
    
    # Deduce score based on local classification
    trust_score = int(round((1.0 - fake_prob) * 100))
    
    # 2. Assign label
    if trust_score >= 70:
        label = "Reliable"
    elif trust_score >= 40:
        label = "Caution"
    else:
        label = "Misleading"
        
    # 3. Build a structured explanation summary of search snippets
    explanation_parts = [
        f"🤖 LOCAL AUDIT NOTE: Deep Web Reasoning is operating in Local Fallback Mode because no GEMINI_API_KEY or ANTHROPIC_API_KEY was found in the environment.",
        f"We searched the internet for reviews related to the claim. Here is the synthesized findings:"
    ]
    
    if search_results:
        for idx, result in enumerate(search_results[:3]):
            explanation_parts.append(
                f"- According to '{result['title']}', details note: \"{result['snippet']}\""
            )
    else:
        explanation_parts.append("No active web results were retrieved for this claim statement.")
        
    explanation_parts.append(
        f"Synthesized locally, our classifiers assign a veracity rating of {trust_score}/100. "
        "Please configure a GEMINI_API_KEY in your .env file to enable state-of-the-art Web Search AI Reasoning."
    )
    
    return {
        "trust_score": trust_score,
        "label": label,
        "explanation": "\n\n".join(explanation_parts),
        "references": search_results[:3]
    }

def run_deep_reasoning_audit(claim_text: str) -> dict:
    """
    Main coordinator for deep reasoning audits.
    1. Searches the internet for information.
    2. Builds a structured fact-checking prompt containing search snippets.
    3. Calls Gemini or Claude to perform Chain-of-Thought auditing and output structured JSON.
    4. Falls back to local classification if LLM APIs are missing or fail.
    """
    # 1. Search the web
    search_results = search.search_internet(claim_text, max_results=5)
    
    # Format search results as text block
    search_text_block = ""
    for idx, res in enumerate(search_results):
        search_text_block += (
            f"[{idx+1}] Title: {res['title']}\n"
            f"    URL: {res['url']}\n"
            f"    Snippet: {res['snippet']}\n\n"
        )
        
    if not search_text_block.strip():
        search_text_block = "No real-time search results returned."
        
    # 2. Build Prompt
    prompt = (
        "You are a professional fact-checking AI reviewer. We have gathered real-time search engine results regarding the following claim.\n\n"
        f"Claim: \"{claim_text}\"\n\n"
        "Search Results:\n"
        f"{search_text_block}\n"
        "Analyze this search information step-by-step to evaluate the veracity of the claim. "
        "Keep in mind that search results may contain rumors, facts, or corrections. You must:\n"
        "1. Synthesize the findings and explain your reasoning analysis clearly in 3-4 paragraphs. "
        "Review if the results support, contradict, or remain inconclusive about the claim.\n"
        "2. Determine an overall Veracity Trust Score between 0 and 100 (where 100 is completely true/factual, and 0 is completely false/malicious disinformation).\n"
        "3. Select an audit label: 'Reliable' (score >= 70), 'Caution' (score 40-69), or 'Misleading' (score < 40).\n"
        "4. Identify 2-3 key source URLs from the search results that verify or debunk the claim.\n\n"
        "You MUST output your response in strict JSON format matching the schema below. Do not add markdown backticks, "
        "introductory greetings, or explanation comments. Output ONLY the JSON block.\n\n"
        "JSON Output Schema:\n"
        "{\n"
        "  \"trust_score\": <integer>,\n"
        "  \"label\": \"<Reliable | Caution | Misleading>\",\n"
        "  \"explanation\": \"<string containing your step-by-step reasoning analysis (include html linebreaks <br/> if needed)>\",\n"
        "  \"references\": [\n"
        "     {\n"
        "       \"title\": \"<string>\",\n"
        "       \"url\": \"<string>\",\n"
        "       \"snippet\": \"<string>\"\n"
        "     }\n"
        "  ]\n"
        "}"
    )
    
    # 3. Check for API keys
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_FACTCHECK_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    
    # 4. Invoke LLM reasoning
    if gemini_key:
        result = run_gemini_reasoning(prompt, gemini_key)
        if result:
            return result
            
    if anthropic_key:
        result = run_anthropic_reasoning(prompt, anthropic_key)
        if result:
            return result
            
    # 5. Fallback to local classification
    return run_fallback_local_reasoning(claim_text, search_results)
