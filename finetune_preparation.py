"""
Prepare labeled data for OpenAI fine-tuning
Converts labeled 483 form data into OpenAI fine-tuning format
"""

import json
import os
from fda_483_processor import FDA483Processor
from typing import List, Dict

def prepare_finetuning_dataset(labeled_data_file: str, output_file: str, api_key: str = None):
    """
    Prepare fine-tuning dataset from labeled data
    
    Args:
        labeled_data_file: Path to JSON file with labeled examples
        output_file: Path to save fine-tuning dataset (JSONL format)
        api_key: OpenAI API key (optional, uses env var if not provided)
    """
    processor = FDA483Processor(api_key=api_key)
    
    # Load labeled data
    with open(labeled_data_file, 'r') as f:
        labeled_data = json.load(f)
    
    # Prepare training data
    training_data = processor.prepare_finetuning_data(labeled_data)
    
    # Save as JSONL (required for OpenAI fine-tuning)
    with open(output_file, 'w') as f:
        for item in training_data:
            f.write(json.dumps(item) + '\n')
    
    print(f"Prepared {len(training_data)} examples for fine-tuning")
    print(f"Saved to: {output_file}")
    
    return training_data

def create_example_labeled_data(output_file: str):
    """Create example labeled data structure"""
    example = [
        {
            "firm_info": {
                "firm": "RC Outsourcing, LLC",
                "fei": "1234567"
            },
            "observations": [
                {
                    "number": 1,
                    "content": "Failure Investigation Deficiencies: Sterility failure of Avastin® with inadequate investigation scope"
                },
                {
                    "number": 2,
                    "content": "Environmental Monitoring Deficiencies: Inadequate environmental monitoring in sterile processing areas"
                },
                {
                    "number": 3,
                    "content": "Trend Investigation Failure: 43 instances of microbial recovery without investigation"
                },
                {
                    "number": 4,
                    "content": "Sterile Processing Contamination: Direct contamination risk during sterile processing (Repeat Violation)"
                }
            ],
            "expected_output": {
                "overall_classification": "OAI",
                "classification_justification": "This inspection would clearly result in OAI classification due to the severity and nature of violations, particularly involving sterile drug products.",
                "relevant_compliance_programs": ["7356.002", "7356.008", "7346.832"],
                "violations": [
                    {
                        "observation_number": 1,
                        "classification": "Critical",
                        "violation_code": "21 CFR 211.192",
                        "rationale": "Sterility failure of Avastin® with inadequate investigation scope",
                        "risk_level": "High",
                        "compliance_program": "7346.832",
                        "is_repeat": False,
                        "action_required": "Immediate corrective action required, potential product recall consideration"
                    },
                    {
                        "observation_number": 2,
                        "classification": "Significant",
                        "violation_code": "21 CFR 211.42",
                        "rationale": "Inadequate environmental monitoring in sterile processing areas",
                        "risk_level": "High",
                        "compliance_program": "7346.832",
                        "is_repeat": True,
                        "action_required": "Enhanced environmental monitoring program implementation"
                    },
                    {
                        "observation_number": 3,
                        "classification": "Significant",
                        "violation_code": "21 CFR 211.192",
                        "rationale": "43 instances of microbial recovery without investigation",
                        "risk_level": "High",
                        "compliance_program": "7356.002",
                        "is_repeat": False,
                        "action_required": "Comprehensive trend analysis and investigation procedures"
                    },
                    {
                        "observation_number": 4,
                        "classification": "Critical",
                        "violation_code": "21 CFR 211.113",
                        "rationale": "Direct contamination risk during sterile processing",
                        "risk_level": "High",
                        "compliance_program": "7346.832",
                        "is_repeat": True,
                        "action_required": "Enhanced regulatory response due to repeat nature"
                    }
                ],
                "follow_up_actions": {
                    "immediate": [
                        "Regulatory Meeting: Required due to sterility failures and repeat violations",
                        "Response Letter: Facility must provide comprehensive corrective action plan",
                        "Product Assessment: Review distribution of affected lots, potential recall evaluation"
                    ],
                    "short_term": [
                        "Warning Letter: Likely issuance due to OAI classification and repeat violations",
                        "Enhanced Surveillance: Increased inspection frequency",
                        "Import Alert Consideration: If products distributed interstate"
                    ],
                    "long_term": [
                        "Follow-Up Inspection: Required to verify corrective action implementation",
                        "Compliance Verification: Focus on sterile processing and environmental monitoring",
                        "Escalation Assessment: Potential enforcement escalation if violations persist"
                    ]
                },
                "risk_prioritization": {
                    "high_priority_elements": [
                        "Sterile Product Contamination: Direct patient safety impact",
                        "Repeat Violations: Indicates systemic compliance failures",
                        "Investigation Inadequacies: Compromises quality system integrity"
                    ],
                    "regulatory_meeting_topics": [
                        "Comprehensive investigation of all lots processed by affected technician",
                        "Environmental monitoring program redesign",
                        "Personnel training and qualification verification",
                        "Quality system effectiveness assessment"
                    ]
                },
                "documentation_requirements": {
                    "facts_system_entries": [
                        "OAI classification with specific violation codes",
                        "Repeat violation flags for Observations 2 and 4",
                        "Risk assessment scores reflecting sterile product concerns",
                        "Follow-up inspection scheduling within 6 months"
                    ],
                    "enforcement_coordination": [
                        "Office of Compliance notification for Warning Letter preparation",
                        "Center for Drug Evaluation and Research (CDER) consultation",
                        "State board of pharmacy notification (compounding facility)"
                    ]
                }
            }
        }
    ]
    
    with open(output_file, 'w') as f:
        json.dump(example, f, indent=2)
    
    print(f"Created example labeled data file: {output_file}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python finetune_preparation.py create_example <output_file.json>")
        print("  python finetune_preparation.py prepare <labeled_data.json> <output_file.jsonl>")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "create_example":
        output_file = sys.argv[2] if len(sys.argv) > 2 else "labeled_data_example.json"
        create_example_labeled_data(output_file)
    
    elif command == "prepare":
        labeled_file = sys.argv[2]
        output_file = sys.argv[3] if len(sys.argv) > 3 else "finetuning_dataset.jsonl"
        prepare_finetuning_dataset(labeled_file, output_file)
    
    else:
        print("Unknown command. Use 'create_example' or 'prepare'")

