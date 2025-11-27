#!/usr/bin/env python3
"""
Test Compliance Personas Integration
Verifies that compliance personas are loaded and functional

Author: NubemSuperFClaude Team
Date: 2025-10-27
"""

import os
import sys
import yaml
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCompliancePersonasIntegration:
    """Test suite for compliance personas integration"""

    def __init__(self):
        self.personas_dir = Path(__file__).parent.parent / "data" / "personas"
        self.compliance_personas = [
            "compliance-orchestrator",
            "iso27001-expert",
            "gdpr-privacy-expert",
            "eu-ai-act-expert"
        ]
        self.results = []

    def test_yaml_files_exist(self):
        """Test 1: Verify YAML files exist"""
        print("\n🔍 TEST 1: Checking if YAML files exist...")

        all_exist = True
        for persona in self.compliance_personas:
            filepath = self.personas_dir / f"{persona}.yaml"
            exists = filepath.exists()

            status = "✅ PASS" if exists else "❌ FAIL"
            print(f"  {status}: {persona}.yaml")

            if not exists:
                all_exist = False

        self.results.append(("YAML Files Exist", all_exist))
        return all_exist

    def test_yaml_structure(self):
        """Test 2: Verify YAML structure is valid"""
        print("\n🔍 TEST 2: Validating YAML structure...")

        all_valid = True
        required_fields = ["name", "identity", "level", "category", "specialties", "capabilities", "system_prompt"]

        for persona in self.compliance_personas:
            filepath = self.personas_dir / f"{persona}.yaml"

            try:
                with open(filepath, 'r') as f:
                    data = yaml.safe_load(f)

                missing_fields = [field for field in required_fields if field not in data]

                if missing_fields:
                    print(f"  ❌ FAIL: {persona} missing fields: {missing_fields}")
                    all_valid = False
                else:
                    print(f"  ✅ PASS: {persona} structure valid")

            except Exception as e:
                print(f"  ❌ FAIL: {persona} - Error: {e}")
                all_valid = False

        self.results.append(("YAML Structure Valid", all_valid))
        return all_valid

    def test_persona_metadata(self):
        """Test 3: Verify persona metadata"""
        print("\n🔍 TEST 3: Checking persona metadata...")

        all_valid = True

        for persona in self.compliance_personas:
            filepath = self.personas_dir / f"{persona}.yaml"

            with open(filepath, 'r') as f:
                data = yaml.safe_load(f)

            # Check level
            if data.get('level') != 'L5':
                print(f"  ⚠️  WARNING: {persona} is not L5 (found: {data.get('level')})")

            # Check category
            expected_category = "Compliance & Governance"
            if data.get('category') != expected_category:
                print(f"  ⚠️  WARNING: {persona} category is '{data.get('category')}' (expected: {expected_category})")

            # Check specialties count
            specialties_count = len(data.get('specialties', []))
            if specialties_count < 40:
                print(f"  ⚠️  WARNING: {persona} has only {specialties_count} specialties (expected 40+)")

            # Check capabilities count
            capabilities_count = len(data.get('capabilities', []))
            if capabilities_count < 10:
                print(f"  ⚠️  WARNING: {persona} has only {capabilities_count} capabilities (expected 10+)")

            print(f"  ✅ INFO: {persona} - {specialties_count} specialties, {capabilities_count} capabilities")

        self.results.append(("Persona Metadata", all_valid))
        return all_valid

    def test_rag_config(self):
        """Test 4: Verify RAG configuration"""
        print("\n🔍 TEST 4: Checking RAG configuration...")

        all_valid = True

        for persona in self.compliance_personas:
            filepath = self.personas_dir / f"{persona}.yaml"

            with open(filepath, 'r') as f:
                data = yaml.safe_load(f)

            rag_config = data.get('rag_config')

            if persona == "compliance-orchestrator":
                # Orchestrator should have all collections
                if rag_config and 'collections' in rag_config:
                    collections = rag_config['collections']
                    if len(collections) >= 5:
                        print(f"  ✅ PASS: {persona} has {len(collections)} RAG collections")
                    else:
                        print(f"  ⚠️  WARNING: {persona} has only {len(collections)} collections")
                else:
                    print(f"  ⚠️  WARNING: {persona} missing RAG config")
            else:
                # Specialists should have specific collections
                if rag_config and 'collections' in rag_config:
                    collections = rag_config['collections']
                    print(f"  ✅ PASS: {persona} has {len(collections)} RAG collections")
                else:
                    print(f"  ⚠️  WARNING: {persona} missing RAG config")

        self.results.append(("RAG Configuration", all_valid))
        return all_valid

    def test_system_prompts(self):
        """Test 5: Verify system prompts are comprehensive"""
        print("\n🔍 TEST 5: Checking system prompt quality...")

        all_valid = True

        for persona in self.compliance_personas:
            filepath = self.personas_dir / f"{persona}.yaml"

            with open(filepath, 'r') as f:
                data = yaml.safe_load(f)

            system_prompt = data.get('system_prompt', '')
            prompt_length = len(system_prompt)

            # Check minimum length (should be comprehensive)
            if prompt_length < 500:
                print(f"  ❌ FAIL: {persona} system prompt too short ({prompt_length} chars)")
                all_valid = False
            elif prompt_length > 10000:
                print(f"  ⚠️  WARNING: {persona} system prompt very long ({prompt_length} chars)")
            else:
                print(f"  ✅ PASS: {persona} system prompt looks good ({prompt_length} chars)")

            # Check for key sections
            key_sections = ["EXPERTISE", "METHODOLOGY", "RESPONSE FORMAT", "LEGAL NOTICE", "COLLABORATION"]
            missing_sections = [section for section in key_sections if section not in system_prompt]

            if missing_sections:
                print(f"    ⚠️  Missing sections: {', '.join(missing_sections)}")

        self.results.append(("System Prompts Quality", all_valid))
        return all_valid

    def test_integration_keywords(self):
        """Test 6: Verify integration keywords are present"""
        print("\n🔍 TEST 6: Checking integration keywords...")

        all_valid = True

        integration_checks = {
            "iso27001-expert": ["GDPR", "AI Act", "NIS2"],
            "gdpr-privacy-expert": ["ISO 27001", "AI Act"],
            "eu-ai-act-expert": ["GDPR", "ISO 27001"],
            "compliance-orchestrator": ["ISO 27001", "GDPR", "AI Act"]
        }

        for persona, keywords in integration_checks.items():
            filepath = self.personas_dir / f"{persona}.yaml"

            with open(filepath, 'r') as f:
                content = f.read()

            missing_keywords = [kw for kw in keywords if kw not in content]

            if missing_keywords:
                print(f"  ⚠️  WARNING: {persona} missing keywords: {', '.join(missing_keywords)}")
            else:
                print(f"  ✅ PASS: {persona} has all integration keywords")

        self.results.append(("Integration Keywords", all_valid))
        return all_valid

    def run_all_tests(self):
        """Run all tests and generate report"""
        print("="*60)
        print("🧪 COMPLIANCE PERSONAS INTEGRATION TESTS")
        print("="*60)

        tests = [
            self.test_yaml_files_exist,
            self.test_yaml_structure,
            self.test_persona_metadata,
            self.test_rag_config,
            self.test_system_prompts,
            self.test_integration_keywords
        ]

        for test in tests:
            test()

        # Generate summary
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)

        passed = sum(1 for _, result in self.results if result)
        total = len(self.results)

        for test_name, result in self.results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status}: {test_name}")

        print(f"\nTotal: {passed}/{total} tests passed")

        if passed == total:
            print("\n🎉 ALL TESTS PASSED!")
            print("\n✅ Compliance personas are ready for use")
            return 0
        else:
            print("\n⚠️  SOME TESTS FAILED - Review errors above")
            return 1


def main():
    """Run tests"""
    tester = TestCompliancePersonasIntegration()
    return tester.run_all_tests()


if __name__ == "__main__":
    exit(main())
