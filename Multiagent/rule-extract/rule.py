"""
Rule Extraction Agent for Sales Commission Calculation

This agent reads OCR output from sales memos and extracts structured rules
(in if-else format) for calculating sales commissions based on various criteria
such as buyer type, block, floor level, unit type, etc.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from openai import AzureOpenAI

# Add Multiagent/ to path so we can import the shared config
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import (
    AZURE_OPENAI_ENDPOINT as endpoint,
    AZURE_OPENAI_API_KEY as subscription_key,
    AZURE_OPENAI_DEPLOYMENT as deployment,
    AZURE_OPENAI_API_VERSION as api_version,
)

model_name = deployment

client = AzureOpenAI(
    api_version=api_version,
    azure_endpoint=endpoint,
    api_key=subscription_key,
)

# System prompt for the Rule Extraction Agent
RULE_EXTRACTION_SYSTEM_PROMPT = """
You are an expert RULE EXTRACTION agent specialized in analyzing sales memos and extracting structured commission calculation rules.

Your task is to analyze the provided OCR output (both text content and table data) from a sales memo and extract ALL rules related to:
1. Sales Commission (REA Commission)
2. Rebates (Bumi Rebate, Standard Rebate, Special Rebate, Additional Rebate)
3. Referral Schemes
4. Price Adjustments
5. Any other conditional pricing or commission logic

EXTRACTION GUIDELINES:
1. Identify ALL conditional logic related to sales commissions and pricing
2. Pay special attention to:
   - Buyer type (Local vs Foreign)
   - Block designation (Block A, Block B, etc.)
   - Floor levels (Low, Mid, High floors with specific level ranges)
   - Unit types (A1, A2, B1, B2, GB1, GB2, C, etc.)
   - Special unit categories (Garden Units, Penthouses)
   - Date ranges for promotional periods
   - Package types (Standard, Foreign, Partially Furnished)

3. Extract rules in clear IF-ELSE conditional format
4. Include all percentage values, monetary amounts, and conditions
5. Preserve the original values and thresholds exactly as stated

OUTPUT FORMAT:
Return a valid JSON object with the following structure:

{
  "memo_reference": "string - the memo reference number if available",
  "effective_period": {
    "start_date": "DD MMM YYYY",
    "end_date": "DD MMM YYYY"
  },
  "project_name": "string",
  "rules": {
    "commission_rules": [
      {
        "rule_id": "COM_001",
        "rule_name": "descriptive name",
        "buyer_type": "local | foreign | all",
        "conditions": [
          {
            "condition": "IF block == 'A'",
            "commission_percentage": 2.0,
            "description": "Block A all levels"
          }
        ],
        "notes": ["any additional notes or conditions"]
      }
    ],
    "rebate_rules": [
      {
        "rule_id": "REB_001",
        "rule_name": "descriptive name",
        "rebate_type": "bumi | standard | special | additional",
        "conditions": [
          {
            "condition": "IF buyer_is_bumi == True",
            "rebate_percentage": 5.0,
            "description": "Bumi Rebate applicable"
          }
        ],
        "calculation_base": "what the rebate is calculated on (e.g., Net Price after Bumi Rebate)",
        "notes": []
      }
    ],
    "referral_rules": [
      {
        "rule_id": "REF_001",
        "rule_name": "descriptive name",
        "referrer_category": "guest | business_associate | staff | bgb",
        "reward_amount": 30000,
        "reward_type": "fixed | percentage",
        "conditions": ["list of eligibility conditions"],
        "payout_timing": "when the reward is paid"
      }
    ],
    "price_adjustment_rules": [
      {
        "rule_id": "PRC_001",
        "rule_name": "descriptive name",
        "adjustment_type": "floor_premium | car_park_premium | block_adjustment",
        "conditions": [
          {
            "condition": "IF floor_level >= 20 AND floor_level < 30",
            "adjustment_amount": 50000,
            "description": "Floor 20 jump premium"
          }
        ]
      }
    ],
    "package_rules": [
      {
        "rule_id": "PKG_001",
        "rule_name": "descriptive name",
        "package_type": "partially_furnished | foreign_package",
        "eligibility": ["conditions for eligibility"],
        "value": "RM amount or percentage",
        "notes": []
      }
    ]
  },
  "pseudo_code": {
    "calculate_commission": "Multi-line pseudo-code representing the complete commission calculation logic",
    "calculate_rebate": "Multi-line pseudo-code for rebate calculation",
    "calculate_final_price": "Multi-line pseudo-code for final price calculation"
  },
  "extraction_confidence": 0.0-1.0,
  "warnings": ["any ambiguities or unclear rules found"]
}

IMPORTANT:
- Extract ALL rules, even partially visible ones (mark confidence appropriately)
- Use exact values from the document (do not interpret or calculate)
- If a rule has multiple tiers or conditions, list ALL of them
- Clearly indicate which rules are CURRENT vs PROPOSED if both are mentioned
- The pseudo_code section should be executable-like logic that combines all rules

EXAMPLE PSEUDO-CODE FORMAT for commission calculation:
```
function calculate_commission(buyer_type, block, floor_level, unit_type, sale_price):
    commission_rate = 0
    
    IF buyer_type == "foreign":
        commission_rate = 7%
        # Note: Calculated on net price after discount, after deducting RM200k for Partially Furnished Package
    
    ELSE IF buyer_type == "local":
        IF block == "A":
            commission_rate = 2%
        ELSE IF block == "B":
            IF floor_level >= 11 AND floor_level <= 19:  # Low floors
                commission_rate = 6%
            ELSE IF floor_level >= 20 AND floor_level <= 29:  # Mid floors
                commission_rate = 5%
            ELSE IF floor_level >= 30 AND floor_level <= 38:  # High floors
                commission_rate = 4%
            ELSE IF is_garden_unit OR is_penthouse:
                commission_rate = 3%
    
    RETURN commission_rate
```

Now analyze the provided OCR output and extract all commission and pricing rules.
"""


def load_ocr_outputs(text_json_path: Path, table_json_path: Path) -> tuple[dict, dict]:
    """
    Load the OCR output JSON files.
    
    Args:
        text_json_path: Path to the text OCR output JSON file
        table_json_path: Path to the table OCR output JSON file
    
    Returns:
        Tuple of (text_data, table_data) dictionaries
    """
    text_data = {}
    table_data = {}
    
    if text_json_path.exists():
        with open(text_json_path, 'r', encoding='utf-8') as f:
            text_data = json.load(f)
        print(f"✓ Loaded text OCR output from: {text_json_path}")
    else:
        print(f"✗ Text OCR file not found: {text_json_path}")
    
    if table_json_path.exists():
        with open(table_json_path, 'r', encoding='utf-8') as f:
            table_data = json.load(f)
        print(f"✓ Loaded table OCR output from: {table_json_path}")
    else:
        print(f"✗ Table OCR file not found: {table_json_path}")
    
    return text_data, table_data


def format_ocr_for_agent(text_data: dict, table_data: dict) -> str:
    """
    Format OCR data into a structured string for the agent to process.
    
    Args:
        text_data: OCR output for text content
        table_data: OCR output for tables
    
    Returns:
        Formatted string containing all OCR content
    """
    formatted_content = []
    
    # Process text OCR output
    formatted_content.append("=" * 80)
    formatted_content.append("TEXT OCR CONTENT")
    formatted_content.append("=" * 80)
    
    if text_data and "results" in text_data:
        for result in text_data["results"]:
            page_num = result.get("page_number", "?")
            formatted_content.append(f"\n--- PAGE {page_num} ---\n")
            
            model_output = result.get("model_output", {})
            if isinstance(model_output, dict) and "pages" in model_output:
                for page in model_output["pages"]:
                    for section in page.get("sections", []):
                        section_type = section.get("type", "unknown")
                        content = section.get("content", "")
                        confidence = section.get("confidence", 0)
                        formatted_content.append(f"[{section_type.upper()}] (confidence: {confidence:.2f})")
                        formatted_content.append(content)
                        formatted_content.append("")
    
    # Process table OCR output
    formatted_content.append("\n" + "=" * 80)
    formatted_content.append("TABLE OCR CONTENT")
    formatted_content.append("=" * 80)
    
    if table_data and "results" in table_data:
        for result in table_data["results"]:
            page_num = result.get("page_number", "?")
            formatted_content.append(f"\n--- PAGE {page_num} TABLES ---\n")
            
            model_output = result.get("model_output", "")
            # The model_output may be a JSON string wrapped in markdown code blocks
            if isinstance(model_output, str):
                # Remove markdown code blocks if present
                clean_output = model_output.strip()
                if clean_output.startswith("```json"):
                    clean_output = clean_output[7:]
                if clean_output.startswith("```"):
                    clean_output = clean_output[3:]
                if clean_output.endswith("```"):
                    clean_output = clean_output[:-3]
                
                try:
                    table_json = json.loads(clean_output)
                    if "tables" in table_json:
                        for table in table_json["tables"]:
                            table_id = table.get("table_id", "unknown")
                            table_title = table.get("table_title", "No title")
                            table_purpose = table.get("table_purpose", "unknown")
                            confidence = table.get("table_confidence", 0)
                            
                            formatted_content.append(f"TABLE: {table_title or table_id}")
                            formatted_content.append(f"Purpose: {table_purpose} | Confidence: {confidence}")
                            formatted_content.append(f"Columns: {table.get('columns', [])}")
                            formatted_content.append("Rows:")
                            for row in table.get("rows", []):
                                formatted_content.append(f"  {row}")
                            formatted_content.append("")
                except json.JSONDecodeError:
                    formatted_content.append(f"Raw table output: {model_output}")
    
    return "\n".join(formatted_content)


def extract_rules(ocr_content: str) -> dict:
    """
    Use the Azure OpenAI model to extract rules from OCR content.
    
    Args:
        ocr_content: Formatted string containing all OCR content
    
    Returns:
        Dictionary containing extracted rules
    """
    user_prompt = f"""
Please analyze the following OCR output from a sales memo and extract all rules related to sales commissions, rebates, referral schemes, and pricing adjustments.

Focus especially on:
1. REA (Real Estate Agent) commission percentages based on buyer type, block, and floor level
2. All types of rebates (Bumi, Standard, Special, Additional)
3. Referral scheme rewards and conditions
4. Floor premiums and car park premiums
5. Special packages (Partially Furnished, Foreign packages)

OCR CONTENT:
{ocr_content}

Extract all rules in the structured JSON format as specified. Generate clear pseudo-code that can be used to implement the commission calculation logic.
"""
    
    print("\n🤖 Sending OCR content to Rule Extraction Agent...")
    print(f"   Content length: {len(ocr_content)} characters")
    
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": RULE_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        max_completion_tokens=8000,
    )
    
    result = response.choices[0].message.content
    
    # Try to parse the response as JSON
    try:
        # Remove markdown code blocks if present
        clean_result = result.strip()
        if clean_result.startswith("```json"):
            clean_result = clean_result[7:]
        if clean_result.startswith("```"):
            clean_result = clean_result[3:]
        if clean_result.endswith("```"):
            clean_result = clean_result[:-3]
        
        rules_dict = json.loads(clean_result)
        return rules_dict
    except json.JSONDecodeError as e:
        print(f"⚠ Warning: Could not parse response as JSON: {e}")
        return {"raw_response": result, "parse_error": str(e)}


def save_rules(rules: dict, output_path: Path) -> None:
    """
    Save extracted rules to a JSON file.
    
    Args:
        rules: Dictionary containing extracted rules
        output_path: Path to save the output JSON file
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved extracted rules to: {output_path}")


def main():
    # Define paths
    artifact_dir = Path(__file__).parent.parent / "artifact"
    text_json_path = artifact_dir / "output-text.json"
    table_json_path = artifact_dir / "output.json"
    output_path = artifact_dir / "extracted-rules.json"
    
    print("=" * 60)
    print("SALES COMMISSION RULE EXTRACTION AGENT")
    print("=" * 60)
    
    # Step 1: Load OCR outputs
    print("\n📂 Loading OCR output files...")
    text_data, table_data = load_ocr_outputs(text_json_path, table_json_path)
    
    # Step 2: Format OCR content for the agent
    print("\n📝 Formatting OCR content...")
    ocr_content = format_ocr_for_agent(text_data, table_data)
    
    # Optional: Preview the formatted content
    print(f"\n📄 Preview of formatted content (first 1000 chars):")
    print("-" * 40)
    print(ocr_content[:1000])
    print("-" * 40)
    
    # Step 3: Extract rules using the agent
    print("\n🔍 Extracting rules from OCR content...")
    rules = extract_rules(ocr_content)
    
    # Step 4: Save the extracted rules
    print("\n💾 Saving extracted rules...")
    save_rules(rules, output_path)
    
    # Step 5: Display summary
    print("\n" + "=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)
    
    if "rules" in rules:
        rule_counts = {
            "Commission Rules": len(rules["rules"].get("commission_rules", [])),
            "Rebate Rules": len(rules["rules"].get("rebate_rules", [])),
            "Referral Rules": len(rules["rules"].get("referral_rules", [])),
            "Price Adjustment Rules": len(rules["rules"].get("price_adjustment_rules", [])),
            "Package Rules": len(rules["rules"].get("package_rules", [])),
        }
        
        for rule_type, count in rule_counts.items():
            print(f"  • {rule_type}: {count}")
        
        if "pseudo_code" in rules:
            print("\n📋 Generated Pseudo-code Preview:")
            print("-" * 40)
            calc_comm = rules["pseudo_code"].get("calculate_commission", "N/A")
            print(calc_comm[:500] + "..." if len(calc_comm) > 500 else calc_comm)
    else:
        print("  ⚠ Rules not properly extracted. Check the output file for details.")
    
    print("\n✅ Rule extraction complete!")
    print(f"   Output saved to: {output_path}")
    
    return rules


if __name__ == "__main__":
    main()
