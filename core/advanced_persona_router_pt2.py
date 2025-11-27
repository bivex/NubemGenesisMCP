#!/usr/bin/env python3
"""
Advanced Persona Router - Part 2: A/B Testing and Metrics
==========================================================

Continuation with A/B testing framework and comprehensive metrics system.
"""

import asyncio
import logging
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import json
from pathlib import Path
import uuid

# Import RoutingMetrics from main module
from .advanced_persona_router import RoutingMetrics

logger = logging.getLogger(__name__)

# ============================================================================
# 4. A/B Testing Framework
# ============================================================================

@dataclass
class ABTestVariant:
    """A/B test variant configuration"""
    variant_id: str
    name: str
    description: str
    routing_strategy: str
    strategy_params: Dict[str, Any]
    traffic_allocation: float  # 0.0-1.0
    is_control: bool = False


@dataclass
class ABTestResult:
    """Individual A/B test result"""
    test_id: str
    variant_id: str
    persona_selected: str
    success: bool
    user_rating: float
    latency_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: Optional[str] = None


class ABTestManager:
    """
    A/B Testing framework for routing strategies
    Allows comparing different routing approaches in production
    """

    def __init__(self, persistence_path: Optional[str] = None):
        self.active_tests: Dict[str, Dict[str, ABTestVariant]] = {}  # test_id -> variants
        self.test_results: Dict[str, List[ABTestResult]] = defaultdict(list)
        self.user_assignments: Dict[str, Dict[str, str]] = {}  # test_id -> {user/session -> variant}
        self.persistence_path = persistence_path

        if persistence_path:
            self.load_state()

    def create_test(self,
                   test_id: str,
                   variants: List[ABTestVariant],
                   auto_normalize: bool = True) -> bool:
        """
        Create new A/B test

        Args:
            test_id: Unique test identifier
            variants: List of test variants
            auto_normalize: Normalize traffic allocations to sum to 1.0

        Returns:
            Success status
        """
        if test_id in self.active_tests:
            logger.warning(f"Test {test_id} already exists")
            return False

        # Validate variants
        if not variants:
            logger.error("No variants provided")
            return False

        # Normalize traffic allocations
        if auto_normalize:
            total_allocation = sum(v.traffic_allocation for v in variants)
            if total_allocation > 0:
                for variant in variants:
                    variant.traffic_allocation /= total_allocation

        # Store variants
        self.active_tests[test_id] = {v.variant_id: v for v in variants}
        self.user_assignments[test_id] = {}

        logger.info(f"Created A/B test {test_id} with {len(variants)} variants")
        return True

    def assign_variant(self,
                      test_id: str,
                      user_id: str,
                      sticky: bool = True) -> Optional[ABTestVariant]:
        """
        Assign user to a test variant

        Args:
            test_id: Test identifier
            user_id: User/session identifier
            sticky: If True, user stays in same variant

        Returns:
            Assigned variant or None
        """
        if test_id not in self.active_tests:
            logger.warning(f"Test {test_id} not found")
            return None

        # Check existing assignment
        if sticky and user_id in self.user_assignments.get(test_id, {}):
            variant_id = self.user_assignments[test_id][user_id]
            return self.active_tests[test_id].get(variant_id)

        # Assign new variant based on traffic allocation
        variants = list(self.active_tests[test_id].values())
        allocations = [v.traffic_allocation for v in variants]

        # Random assignment weighted by allocation
        assigned_variant = np.random.choice(variants, p=allocations)

        # Store assignment
        if test_id not in self.user_assignments:
            self.user_assignments[test_id] = {}
        self.user_assignments[test_id][user_id] = assigned_variant.variant_id

        logger.debug(f"Assigned user {user_id} to variant {assigned_variant.variant_id}")
        return assigned_variant

    def record_result(self, result: ABTestResult):
        """Record A/B test result"""
        self.test_results[result.test_id].append(result)

        # Persist periodically
        if len(self.test_results[result.test_id]) % 100 == 0:
            self.save_state()

    def get_test_statistics(self, test_id: str) -> Dict[str, Any]:
        """
        Calculate comprehensive statistics for A/B test

        Args:
            test_id: Test identifier

        Returns:
            Statistics dictionary
        """
        if test_id not in self.active_tests:
            return {'error': 'Test not found'}

        results = self.test_results.get(test_id, [])
        if not results:
            return {'error': 'No results yet', 'sample_size': 0}

        # Group by variant
        variant_stats = {}
        for variant_id in self.active_tests[test_id].keys():
            variant_results = [r for r in results if r.variant_id == variant_id]

            if not variant_results:
                variant_stats[variant_id] = {
                    'sample_size': 0,
                    'success_rate': 0.0,
                    'avg_rating': 0.0,
                    'avg_latency_ms': 0.0
                }
                continue

            variant_stats[variant_id] = {
                'sample_size': len(variant_results),
                'success_rate': sum(r.success for r in variant_results) / len(variant_results),
                'avg_rating': np.mean([r.user_rating for r in variant_results]),
                'avg_latency_ms': np.mean([r.latency_ms for r in variant_results]),
                'p95_latency_ms': np.percentile([r.latency_ms for r in variant_results], 95),
                'persona_distribution': self._get_persona_distribution(variant_results)
            }

        # Calculate statistical significance (simplified chi-square test)
        significance = self._calculate_significance(variant_stats)

        return {
            'test_id': test_id,
            'total_samples': len(results),
            'variant_stats': variant_stats,
            'statistical_significance': significance,
            'recommended_winner': self._recommend_winner(variant_stats),
            'duration_days': (datetime.now() - results[0].timestamp).days if results else 0
        }

    def _get_persona_distribution(self, results: List[ABTestResult]) -> Dict[str, int]:
        """Get distribution of personas selected"""
        distribution = defaultdict(int)
        for result in results:
            distribution[result.persona_selected] += 1
        return dict(distribution)

    def _calculate_significance(self, variant_stats: Dict) -> Dict[str, Any]:
        """
        Calculate statistical significance between variants
        Uses simplified z-test for proportions
        """
        if len(variant_stats) < 2:
            return {'significant': False, 'reason': 'Need at least 2 variants'}

        # Find control and treatment
        control_id = None
        treatment_ids = []

        for vid, stats in variant_stats.items():
            if stats['sample_size'] >= 30:  # Minimum sample size
                if control_id is None:
                    control_id = vid
                else:
                    treatment_ids.append(vid)

        if not control_id or not treatment_ids:
            return {'significant': False, 'reason': 'Insufficient sample size (need 30+ per variant)'}

        control_stats = variant_stats[control_id]

        # Compare each treatment to control
        comparisons = {}
        for treatment_id in treatment_ids:
            treatment_stats = variant_stats[treatment_id]

            # Z-test for success rates
            p1 = control_stats['success_rate']
            p2 = treatment_stats['success_rate']
            n1 = control_stats['sample_size']
            n2 = treatment_stats['sample_size']

            # Pooled proportion
            p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)

            # Z-statistic
            if p_pool * (1 - p_pool) > 0:
                z = (p2 - p1) / np.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
                p_value = 2 * (1 - self._normal_cdf(abs(z)))

                comparisons[treatment_id] = {
                    'z_statistic': float(z),
                    'p_value': float(p_value),
                    'significant': p_value < 0.05,
                    'improvement': (p2 - p1) / p1 if p1 > 0 else 0.0
                }

        return {
            'control_variant': control_id,
            'comparisons': comparisons,
            'overall_significant': any(c['significant'] for c in comparisons.values())
        }

    def _normal_cdf(self, x: float) -> float:
        """Cumulative distribution function for standard normal"""
        from math import erf, sqrt
        return (1.0 + erf(x / sqrt(2.0))) / 2.0

    def _recommend_winner(self, variant_stats: Dict) -> Optional[str]:
        """
        Recommend winning variant based on composite score

        Composite score = 0.4 * success_rate + 0.4 * avg_rating + 0.2 * (1 - normalized_latency)
        """
        if not variant_stats:
            return None

        composite_scores = {}
        max_latency = max(s['avg_latency_ms'] for s in variant_stats.values() if s['sample_size'] > 0)

        for variant_id, stats in variant_stats.items():
            if stats['sample_size'] < 30:  # Minimum sample size
                continue

            normalized_latency = stats['avg_latency_ms'] / max_latency if max_latency > 0 else 0
            composite_score = (
                0.4 * stats['success_rate'] +
                0.4 * stats['avg_rating'] +
                0.2 * (1.0 - normalized_latency)
            )
            composite_scores[variant_id] = composite_score

        if not composite_scores:
            return None

        return max(composite_scores.items(), key=lambda x: x[1])[0]

    def end_test(self, test_id: str) -> Dict[str, Any]:
        """
        End A/B test and return final results

        Args:
            test_id: Test identifier

        Returns:
            Final statistics
        """
        if test_id not in self.active_tests:
            return {'error': 'Test not found'}

        # Get final statistics
        final_stats = self.get_test_statistics(test_id)

        # Archive test
        self.save_state()

        logger.info(f"Ended A/B test {test_id}")
        return final_stats

    def save_state(self):
        """Save A/B test state to disk"""
        if not self.persistence_path:
            return

        data = {
            'active_tests': {
                test_id: {
                    vid: {
                        'variant_id': v.variant_id,
                        'name': v.name,
                        'description': v.description,
                        'routing_strategy': v.routing_strategy,
                        'strategy_params': v.strategy_params,
                        'traffic_allocation': v.traffic_allocation,
                        'is_control': v.is_control
                    }
                    for vid, v in variants.items()
                }
                for test_id, variants in self.active_tests.items()
            },
            'user_assignments': self.user_assignments,
            'test_results': {
                test_id: [
                    {
                        'test_id': r.test_id,
                        'variant_id': r.variant_id,
                        'persona_selected': r.persona_selected,
                        'success': r.success,
                        'user_rating': r.user_rating,
                        'latency_ms': r.latency_ms,
                        'timestamp': r.timestamp.isoformat(),
                        'session_id': r.session_id
                    }
                    for r in results
                ]
                for test_id, results in self.test_results.items()
            }
        }

        Path(self.persistence_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.persistence_path, 'w') as f:
            json.dump(data, f, indent=2)

    def load_state(self):
        """Load A/B test state from disk"""
        if not self.persistence_path or not Path(self.persistence_path).exists():
            return

        try:
            with open(self.persistence_path, 'r') as f:
                data = json.load(f)

            # Load active tests
            for test_id, variants_dict in data.get('active_tests', {}).items():
                variants = [
                    ABTestVariant(**v) for v in variants_dict.values()
                ]
                self.active_tests[test_id] = {v.variant_id: v for v in variants}

            # Load user assignments
            self.user_assignments = data.get('user_assignments', {})

            # Load test results
            for test_id, results_list in data.get('test_results', {}).items():
                self.test_results[test_id] = [
                    ABTestResult(
                        test_id=r['test_id'],
                        variant_id=r['variant_id'],
                        persona_selected=r['persona_selected'],
                        success=r['success'],
                        user_rating=r['user_rating'],
                        latency_ms=r['latency_ms'],
                        timestamp=datetime.fromisoformat(r['timestamp']),
                        session_id=r.get('session_id')
                    )
                    for r in results_list
                ]

            logger.info(f"Loaded A/B test state from {self.persistence_path}")
        except Exception as e:
            logger.error(f"Failed to load A/B test state: {e}")


# ============================================================================
# 5. Comprehensive Metrics System
# ============================================================================

class RoutingMetricsCollector:
    """
    Comprehensive metrics collection and analysis for routing system
    Tracks performance, usage patterns, and provides insights
    """

    def __init__(self, persistence_path: Optional[str] = None):
        self.metrics = RoutingMetrics()
        self.detailed_history: List[Dict[str, Any]] = []
        self.time_series_data: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
        self.persistence_path = persistence_path
        self.start_time = datetime.now()

    def record_routing(self,
                      result: 'RoutingResult',
                      context: 'RoutingContext',
                      success: bool,
                      user_rating: Optional[float] = None):
        """Record a routing event with full details"""

        # Update basic metrics
        self.metrics.total_requests += 1
        if success:
            self.metrics.successful_routings += 1

        # Update strategy usage
        strategy = result.strategy_used
        self.metrics.strategy_usage[strategy] = self.metrics.strategy_usage.get(strategy, 0) + 1

        # Update persona usage
        persona = result.primary_persona
        self.metrics.persona_usage[persona] = self.metrics.persona_usage.get(persona, 0) + 1

        # Update persona success rate
        if persona not in self.metrics.persona_success_rate:
            self.metrics.persona_success_rate[persona] = 0.0

        current_success_rate = self.metrics.persona_success_rate[persona]
        persona_total = self.metrics.persona_usage[persona]
        self.metrics.persona_success_rate[persona] = (
            (current_success_rate * (persona_total - 1) + (1.0 if success else 0.0)) / persona_total
        )

        # Update averages
        total = self.metrics.total_requests
        self.metrics.average_confidence = (
            (self.metrics.average_confidence * (total - 1) + result.confidence_score) / total
        )
        self.metrics.average_latency_ms = (
            (self.metrics.average_latency_ms * (total - 1) + result.routing_time_ms) / total
        )

        if user_rating is not None:
            self.metrics.average_user_rating = (
                (self.metrics.average_user_rating * (total - 1) + user_rating) / total
            )

        # Record detailed history
        self.detailed_history.append({
            'timestamp': datetime.now().isoformat(),
            'task': context.task[:100],  # Truncate for storage
            'task_type': context.task_type,
            'complexity': context.complexity_level,
            'primary_persona': result.primary_persona,
            'support_personas': result.support_personas,
            'strategy': result.strategy_used,
            'confidence': result.confidence_score,
            'latency_ms': result.routing_time_ms,
            'success': success,
            'user_rating': user_rating
        })

        # Keep last 10000 records
        if len(self.detailed_history) > 10000:
            self.detailed_history.pop(0)

        # Update time series data
        now = datetime.now()
        self.time_series_data['latency'].append((now, result.routing_time_ms))
        self.time_series_data['confidence'].append((now, result.confidence_score))
        if user_rating is not None:
            self.time_series_data['rating'].append((now, user_rating))

        # Trim old time series data (keep last 24 hours)
        cutoff = now - timedelta(hours=24)
        for key in self.time_series_data:
            self.time_series_data[key] = [
                (t, v) for t, v in self.time_series_data[key] if t > cutoff
            ]

    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary"""
        return {
            'overview': {
                'total_requests': self.metrics.total_requests,
                'successful_routings': self.metrics.successful_routings,
                'success_rate': self.metrics.successful_routings / self.metrics.total_requests
                               if self.metrics.total_requests > 0 else 0.0,
                'average_confidence': round(self.metrics.average_confidence, 3),
                'average_latency_ms': round(self.metrics.average_latency_ms, 2),
                'average_user_rating': round(self.metrics.average_user_rating, 3),
                'uptime_hours': (datetime.now() - self.start_time).total_seconds() / 3600
            },
            'strategy_usage': self.metrics.strategy_usage,
            'top_personas': self._get_top_personas(10),
            'persona_performance': self._get_persona_performance(),
            'time_series': self._get_time_series_summary()
        }

    def _get_top_personas(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get top N most used personas with stats"""
        sorted_personas = sorted(
            self.metrics.persona_usage.items(),
            key=lambda x: x[1],
            reverse=True
        )[:n]

        return [
            {
                'persona': persona,
                'usage_count': count,
                'success_rate': self.metrics.persona_success_rate.get(persona, 0.0),
                'usage_percentage': (count / self.metrics.total_requests * 100)
                                   if self.metrics.total_requests > 0 else 0.0
            }
            for persona, count in sorted_personas
        ]

    def _get_persona_performance(self) -> Dict[str, Any]:
        """Analyze persona performance"""
        if not self.metrics.persona_success_rate:
            return {}

        best_performer = max(
            self.metrics.persona_success_rate.items(),
            key=lambda x: x[1]
        )
        worst_performer = min(
            self.metrics.persona_success_rate.items(),
            key=lambda x: x[1]
        )

        return {
            'best_performer': {
                'persona': best_performer[0],
                'success_rate': round(best_performer[1], 3)
            },
            'worst_performer': {
                'persona': worst_performer[0],
                'success_rate': round(worst_performer[1], 3)
            },
            'average_success_rate': round(
                np.mean(list(self.metrics.persona_success_rate.values())), 3
            )
        }

    def _get_time_series_summary(self) -> Dict[str, Any]:
        """Summarize time series data"""
        summary = {}
        for key, data in self.time_series_data.items():
            if not data:
                continue
            values = [v for _, v in data]
            summary[key] = {
                'current': values[-1] if values else 0,
                'min': min(values),
                'max': max(values),
                'avg': np.mean(values),
                'p50': np.percentile(values, 50),
                'p95': np.percentile(values, 95),
                'p99': np.percentile(values, 99),
                'samples': len(values)
            }
        return summary

    def get_insights(self) -> List[str]:
        """Generate actionable insights from metrics"""
        insights = []

        # Check success rate
        success_rate = (self.metrics.successful_routings / self.metrics.total_requests
                       if self.metrics.total_requests > 0 else 0)
        if success_rate < 0.8:
            insights.append(f"⚠️ Low success rate ({success_rate:.1%}). Consider reviewing routing strategies.")

        # Check latency
        if self.metrics.average_latency_ms > 1000:
            insights.append(f"⚠️ High average latency ({self.metrics.average_latency_ms:.0f}ms). Consider caching or optimization.")

        # Check persona distribution
        if self.metrics.persona_usage:
            max_usage = max(self.metrics.persona_usage.values())
            total = sum(self.metrics.persona_usage.values())
            if max_usage / total > 0.5:
                insights.append("⚠️ High concentration on single persona. May indicate routing imbalance.")

        # Check confidence
        if self.metrics.average_confidence < 0.6:
            insights.append(f"⚠️ Low average confidence ({self.metrics.average_confidence:.2f}). Routes may be uncertain.")

        # Check user rating
        if self.metrics.average_user_rating > 0 and self.metrics.average_user_rating < 0.7:
            insights.append(f"⚠️ Low user satisfaction ({self.metrics.average_user_rating:.2f}). Review persona quality.")

        if not insights:
            insights.append("✅ All metrics look healthy!")

        return insights

    def export_to_file(self, filepath: str, format: str = 'json'):
        """Export metrics to file"""
        data = {
            'summary': self.get_summary(),
            'insights': self.get_insights(),
            'detailed_history': self.detailed_history[-1000:],  # Last 1000 records
            'export_timestamp': datetime.now().isoformat()
        }

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        if format == 'json':
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Metrics exported to {filepath}")


# ============================================================================
# Export all classes
# ============================================================================

__all__ = [
    'ABTestVariant',
    'ABTestResult',
    'ABTestManager',
    'RoutingMetricsCollector'
]
