#!/usr/bin/env python3
"""
Test suite for the unified persona system
Verifies all personas are loaded and functional
"""

import unittest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.personas_unified import UnifiedPersonaManager


class TestUnifiedPersonas(unittest.TestCase):
    """Test the unified persona system"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.manager = UnifiedPersonaManager()
    
    def test_persona_loading(self):
        """Test that all personas are loaded"""
        total = self.manager.get_total_persona_count()
        print(f"\n✅ Total personas loaded: {total}")
        
        # We should have at least 39 personas
        self.assertGreaterEqual(total, 39, "Should have at least 39 personas")
        
        # Check categories
        categories = self.manager.list_personas_by_category()
        print(f"📊 Categories: {list(categories.keys())}")
        
        self.assertIn('core', categories)
        self.assertIn('specialists', categories)
        self.assertIn('automation', categories)
        self.assertIn('cloud', categories)
    
    def test_core_personas_exist(self):
        """Test that all 16 core personas exist"""
        core_personas = [
            'architect', 'frontend', 'backend', 'analyzer', 'security',
            'performance', 'documenter', 'tester', 'devops', 'refactorer',
            'mentor', 'ai-specialist', 'data-engineer', 'cloud-specialist',
            'product-manager', 'infrastructure-engineer'
        ]
        
        for persona_name in core_personas:
            persona = self.manager.get_persona(persona_name)
            self.assertIsNotNone(persona, f"Core persona {persona_name} should exist")
            print(f"  ✓ {persona_name}: {persona['identity'][:50]}...")
    
    def test_specialist_personas_exist(self):
        """Test that all 11 specialist personas exist"""
        specialist_personas = [
            'iteration-intelligence', 'n8n-specialist', 'flowise-specialist',
            'maker-specialist', 'huggingface-specialist', 'testing-specialist',
            'cicd-specialist', 'google-workspace-specialist', 
            'office365-specialist', 'azure-cloud-specialist', 
            'huawei-cloud-specialist'
        ]
        
        for persona_name in specialist_personas:
            persona = self.manager.get_persona(persona_name)
            self.assertIsNotNone(persona, f"Specialist persona {persona_name} should exist")
            print(f"  ✓ {persona_name}: Level {persona['level']}")
    
    def test_additional_personas_exist(self):
        """Test additional personas from framework"""
        additional_personas = [
            'fullstack', 'innovator', 'data-analyst',
            'blockchain-specialist', 'mobile-developer', 'game-developer',
            'iot-specialist', 'cybersecurity-specialist', 'sre-specialist',
            'accessibility-specialist', 'ux-designer', 'database-administrator'
        ]
        
        for persona_name in additional_personas:
            persona = self.manager.get_persona(persona_name)
            self.assertIsNotNone(persona, f"Additional persona {persona_name} should exist")
    
    def test_persona_capabilities(self):
        """Test that personas have proper capabilities"""
        # Test architect persona
        architect = self.manager.get_persona('architect')
        self.assertIn('design_system', architect['capabilities'])
        self.assertIn('create_adr', architect['capabilities'])
        
        # Test AI specialist
        ai_specialist = self.manager.get_persona('ai-specialist')
        self.assertIn('implement_ai', ai_specialist['capabilities'])
        self.assertIn('implement_rag', ai_specialist['capabilities'])
        
        # Test n8n specialist
        n8n = self.manager.get_persona('n8n-specialist')
        self.assertIn('design_workflows', n8n['capabilities'])
        self.assertEqual(n8n['level'], 'L5')
    
    def test_persona_collaboration(self):
        """Test persona collaboration networks"""
        architect = self.manager.get_persona('architect')
        self.assertIsNotNone(architect['collaborates_with'])
        self.assertIn('backend', architect['collaborates_with'])
        self.assertIn('devops', architect['collaborates_with'])
    
    def test_find_best_persona(self):
        """Test finding the best persona for a task"""
        # Test architecture task
        best = self.manager.find_best_persona("design microservices architecture")
        self.assertEqual(best, 'architect')
        
        # Test frontend task
        best = self.manager.find_best_persona("create React component")
        self.assertEqual(best, 'frontend')
        
        # Test security task
        best = self.manager.find_best_persona("perform security audit")
        self.assertIn(best, ['security', 'cybersecurity-specialist'])
        
        # Test automation task
        best = self.manager.find_best_persona("create workflow automation with n8n")
        self.assertIn(best, ['n8n-specialist', 'maker-specialist'])
    
    def test_persona_activation(self):
        """Test persona activation and deactivation"""
        # Activate some personas
        self.assertTrue(self.manager.activate_persona('architect'))
        self.assertTrue(self.manager.activate_persona('frontend'))
        self.assertTrue(self.manager.activate_persona('n8n-specialist'))
        
        # Check active personas
        active = self.manager.active_personas
        self.assertIn('architect', active)
        self.assertIn('frontend', active)
        self.assertIn('n8n-specialist', active)
    
    def test_persona_statistics(self):
        """Test persona system statistics"""
        stats = self.manager.get_statistics()
        
        print(f"\n📈 Persona System Statistics:")
        print(f"  - Total personas: {stats['total_personas']}")
        print(f"  - Categories: {stats['categories']}")
        print(f"  - Level distribution: {stats['level_distribution']}")
        print(f"  - Average capabilities: {stats['average_capabilities']:.1f}")
        
        self.assertGreater(stats['total_personas'], 0)
        self.assertIn('L5', stats['level_distribution'])
        self.assertIn('L4', stats['level_distribution'])
        
        # Verify category counts
        self.assertGreater(stats['categories']['core'], 0)
        self.assertGreater(stats['categories']['specialists'], 0)
    
    def test_persona_confidence_scores(self):
        """Test persona confidence scoring"""
        personas_to_test = ['architect', 'frontend', 'security', 'ai-specialist']
        
        for persona_name in personas_to_test:
            persona = self.manager.get_persona(persona_name)
            scores = persona['confidence_scores']
            
            # Each persona should have confidence scores
            self.assertIsNotNone(scores)
            self.assertGreater(len(scores), 0)
            
            # Scores should be between 0 and 1
            for capability, score in scores.items():
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 1)
    
    def test_all_personas_have_commands(self):
        """Test that all personas have commands defined"""
        all_personas = self.manager.list_personas()
        
        for persona_name in all_personas:
            persona = self.manager.get_persona(persona_name)
            commands = persona['commands']
            
            # Each persona should have at least base commands
            self.assertIsNotNone(commands)
            self.assertGreater(len(commands), 0)
            
            # Check command structure
            for cmd in commands:
                self.assertIn('name', cmd)
                self.assertIn('description', cmd)


def run_tests():
    """Run all tests with detailed output"""
    print("🧪 Testing Unified Persona System")
    print("=" * 60)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestUnifiedPersonas)
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ All tests passed successfully!")
        print(f"   - Tests run: {result.testsRun}")
        print(f"   - Time: {sum(getattr(test, '_elapsed', 0) for test in result.tests):.2f}s")
    else:
        print("❌ Some tests failed")
        print(f"   - Failures: {len(result.failures)}")
        print(f"   - Errors: {len(result.errors)}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    
    # Additional reporting
    manager = UnifiedPersonaManager()
    print("\n📊 Final Persona Count by Category:")
    for category, personas in manager.list_personas_by_category().items():
        if personas:
            print(f"  {category.upper()}: {len(personas)} personas")
    
    print(f"\n🎯 Total Personas in System: {manager.get_total_persona_count()}")
    
    sys.exit(0 if success else 1)