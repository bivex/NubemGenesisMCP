#!/usr/bin/env python3
"""
Response Synthesizer - Synthesizes final response from swarm consensus
Creates coherent, unified response from multiple persona perspectives
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class SynthesizedResponse:
    """Final synthesized response"""
    content: str
    summary: str
    key_recommendations: List[str]
    confidence: float
    sources: List[str]  # Personas that contributed
    metadata: Dict[str, Any]


class ResponseSynthesizer:
    """
    Response Synthesizer - Creates unified response from swarm results

    Takes consensus analysis and individual responses, produces
    coherent final response that represents collective wisdom
    """

    def __init__(self):
        """Initialize Response Synthesizer"""
        self.synthesis_count = 0

    def synthesize(
        self,
        query: str,
        swarm_result: Any,  # SwarmResult object
        consensus_result: Any,  # ConsensusResult object
        style: str = "comprehensive"  # "comprehensive", "concise", "technical"
    ) -> SynthesizedResponse:
        """
        Synthesize final response from swarm and consensus results

        Args:
            query: Original query
            swarm_result: SwarmResult with all persona responses
            consensus_result: ConsensusResult with consensus analysis
            style: Output style preference

        Returns:
            SynthesizedResponse with unified response
        """
        logger.info(f"🔮 Synthesizing response from {len(swarm_result.personas)} personas")
        logger.info(f"   Style: {style}")

        # Build response sections
        sections = []

        # 1. Executive Summary
        summary = self._create_summary(query, consensus_result)
        sections.append(f"## Summary\n\n{summary}")

        # 2. Key Consensus Points
        if consensus_result.consensus_points:
            consensus_section = self._create_consensus_section(consensus_result)
            sections.append(consensus_section)

        # 3. Detailed Analysis (if comprehensive)
        if style == "comprehensive":
            analysis_section = self._create_analysis_section(swarm_result, consensus_result)
            sections.append(analysis_section)

        # 4. Recommendations
        recommendations = self._create_recommendations(consensus_result)
        sections.append(f"## Recommendations\n\n{recommendations}")

        # 5. Confidence Assessment
        if style in ["comprehensive", "technical"]:
            confidence_section = self._create_confidence_section(swarm_result, consensus_result)
            sections.append(confidence_section)

        # 6. Expert Attribution (who contributed)
        attribution = self._create_attribution(swarm_result)
        sections.append(f"## Expert Consultation\n\n{attribution}")

        # Combine all sections
        full_content = "\n\n---\n\n".join(sections)

        # Extract key recommendations
        key_recs = self._extract_key_recommendations(consensus_result)

        # Calculate final confidence
        final_confidence = self._calculate_final_confidence(swarm_result, consensus_result)

        # Track sources
        sources = [r.persona_name for r in swarm_result.individual_responses if r.success]

        self.synthesis_count += 1

        result = SynthesizedResponse(
            content=full_content,
            summary=summary,
            key_recommendations=key_recs,
            confidence=final_confidence,
            sources=sources,
            metadata={
                "query": query,
                "style": style,
                "consensus_agreement": consensus_result.agreement_score,
                "personas_consulted": len(swarm_result.personas),
                "successful_responses": swarm_result.success_count,
                "synthesis_number": self.synthesis_count
            }
        )

        logger.info(f"✅ Response synthesized: {len(full_content)} chars, confidence={final_confidence:.2f}")

        return result

    def _create_summary(self, query: str, consensus_result) -> str:
        """Create executive summary"""
        summary_parts = []

        # Start with query context
        summary_parts.append(f"Based on analysis of your query: \"{query}\"")

        # Add agreement level
        agreement_level = self._get_agreement_level(consensus_result.agreement_score)
        summary_parts.append(f"\n\nExpert consensus shows **{agreement_level}** agreement across perspectives.")

        # Add dominant themes if available
        if consensus_result.dominant_themes:
            themes = ", ".join(consensus_result.dominant_themes[:3])
            summary_parts.append(f"Key themes identified: {themes}.")

        # Add recommendation preview
        summary_parts.append(f"\n\n{consensus_result.recommended_action}")

        return "".join(summary_parts)

    def _create_consensus_section(self, consensus_result) -> str:
        """Create section showing consensus points"""
        lines = ["## Areas of Expert Agreement\n"]

        # Group by category
        unanimous = [cp for cp in consensus_result.consensus_points if cp.category == "unanimous"]
        majority = [cp for cp in consensus_result.consensus_points if cp.category == "majority"]

        if unanimous:
            lines.append("### Unanimous Agreement\n")
            for i, point in enumerate(unanimous, 1):
                lines.append(f"{i}. {point.content}")
                lines.append(f"   *All experts agree ({len(point.supporting_personas)} personas)*\n")

        if majority:
            lines.append("\n### Majority Consensus\n")
            for i, point in enumerate(majority, 1):
                lines.append(f"{i}. {point.content}")
                total_responses = consensus_result.metadata.get('total_responses', 0)
                lines.append(f"   *Supported by {len(point.supporting_personas)} of {total_responses} experts*\n")

        return "\n".join(lines)

    def _create_analysis_section(self, swarm_result, consensus_result) -> str:
        """Create detailed analysis section"""
        lines = ["## Detailed Analysis\n"]

        # Add expert perspectives
        lines.append("### Expert Perspectives\n")

        for response in swarm_result.individual_responses:
            if response.success:
                lines.append(f"**{response.persona_name}** ({response.confidence:.0%} confidence):")
                # Truncate long responses
                truncated = response.response[:200] + "..." if len(response.response) > 200 else response.response
                lines.append(f"{truncated}\n")

        # Add disagreements if any
        if consensus_result.disagreement_points:
            lines.append("\n### Points of Discussion\n")
            lines.append("*Areas where expert opinions vary:*\n")

            for disagreement in consensus_result.disagreement_points[:3]:  # Top 3
                lines.append(f"- **{disagreement.topic.capitalize()}**: Different perspectives on implementation")

        return "\n".join(lines)

    def _create_recommendations(self, consensus_result) -> str:
        """Create recommendations section"""
        lines = []

        # Get top consensus points as recommendations
        top_points = consensus_result.consensus_points[:5]

        for i, point in enumerate(top_points, 1):
            # Convert consensus point to actionable recommendation
            if point.category == "unanimous":
                prefix = "✅ **Critical**:"
            elif point.category == "majority":
                prefix = "📌 **Important**:"
            else:
                prefix = "💡 **Consider**:"

            lines.append(f"{i}. {prefix} {point.content}")

        if not lines:
            lines.append("Continue analysis for specific recommendations.")

        return "\n".join(lines)

    def _create_confidence_section(self, swarm_result, consensus_result) -> str:
        """Create confidence assessment section"""
        lines = ["## Confidence Assessment\n"]

        # Overall confidence
        overall = consensus_result.confidence
        lines.append(f"**Overall Confidence**: {overall:.0%}")

        # Factors
        lines.append("\n**Key Factors**:")
        lines.append(f"- Expert Agreement: {consensus_result.agreement_score:.0%}")
        lines.append(f"- Successful Consultations: {swarm_result.success_count}/{len(swarm_result.personas)}")
        lines.append(f"- Response Quality: {self._assess_response_quality(swarm_result)}")

        return "\n".join(lines)

    def _create_attribution(self, swarm_result) -> str:
        """Create expert attribution section"""
        lines = []

        successful_personas = [r.persona_name for r in swarm_result.individual_responses if r.success]

        lines.append(f"This analysis incorporates perspectives from {len(successful_personas)} specialized experts:")
        lines.append("")

        for persona in successful_personas:
            # Humanize persona names
            display_name = persona.replace("-", " ").title()
            lines.append(f"- **{display_name}**")

        lines.append("")
        lines.append(f"*Total analysis time: {swarm_result.total_time_ms}ms*")

        return "\n".join(lines)

    def _extract_key_recommendations(self, consensus_result) -> List[str]:
        """Extract key recommendations as list"""
        recommendations = []

        for point in consensus_result.consensus_points[:5]:
            # Simplify to actionable statement
            rec = point.content.strip()
            if rec:
                recommendations.append(rec)

        return recommendations

    def _calculate_final_confidence(self, swarm_result, consensus_result) -> float:
        """Calculate final confidence score"""
        # Base confidence from consensus
        confidence = consensus_result.confidence

        # Adjust for success rate
        success_rate = swarm_result.success_count / len(swarm_result.personas)
        confidence *= success_rate

        # Boost for high agreement
        if consensus_result.agreement_score > 0.8:
            confidence *= 1.1

        return min(confidence, 1.0)

    def _get_agreement_level(self, score: float) -> str:
        """Convert agreement score to human-readable level"""
        if score >= 0.9:
            return "very strong"
        elif score >= 0.75:
            return "strong"
        elif score >= 0.6:
            return "good"
        elif score >= 0.4:
            return "moderate"
        else:
            return "limited"

    def _assess_response_quality(self, swarm_result) -> str:
        """Assess overall response quality"""
        avg_length = sum(len(r.response) for r in swarm_result.individual_responses) / len(swarm_result.individual_responses)

        if avg_length > 500:
            return "Detailed"
        elif avg_length > 200:
            return "Comprehensive"
        else:
            return "Concise"

    def get_stats(self) -> Dict[str, Any]:
        """Get synthesis statistics"""
        return {
            "total_syntheses": self.synthesis_count
        }


# Convenience function
def synthesize_response(
    query: str,
    swarm_result: Any,
    consensus_result: Any,
    style: str = "comprehensive"
) -> SynthesizedResponse:
    """Synthesize response (convenience function)"""
    synthesizer = ResponseSynthesizer()
    return synthesizer.synthesize(query, swarm_result, consensus_result, style)


if __name__ == "__main__":
    # Test Response Synthesizer
    print("=" * 80)
    print("RESPONSE SYNTHESIZER TEST")
    print("=" * 80)

    # This would normally come from swarm_executor and consensus_builder
    # Using mock data for testing

    from dataclasses import dataclass
    from typing import List

    @dataclass
    class MockPersonaResponse:
        persona_name: str
        response: str
        confidence: float
        execution_time_ms: int
        success: bool

    @dataclass
    class MockSwarmResult:
        query: str
        personas: List[str]
        individual_responses: List[MockPersonaResponse]
        execution_mode: str
        total_time_ms: int
        success_count: int
        failure_count: int

    @dataclass
    class MockConsensusPoint:
        content: str
        supporting_personas: List[str]
        confidence: float
        category: str

    @dataclass
    class MockConsensusResult:
        agreement_score: float
        consensus_points: List[MockConsensusPoint]
        disagreement_points: List
        dominant_themes: List[str]
        recommended_action: str
        confidence: float
        metadata: dict

    # Create mock data
    mock_swarm = MockSwarmResult(
        query="Design a scalable microservices architecture",
        personas=["system-architect", "backend-developer", "devops-engineer"],
        individual_responses=[
            MockPersonaResponse("system-architect", "Use API gateway pattern with service discovery...", 0.9, 150, True),
            MockPersonaResponse("backend-developer", "Implement event-driven architecture with message queues...", 0.85, 140, True),
            MockPersonaResponse("devops-engineer", "Deploy on Kubernetes with horizontal pod autoscaling...", 0.88, 160, True)
        ],
        execution_mode="parallel",
        total_time_ms=160,
        success_count=3,
        failure_count=0
    )

    mock_consensus = MockConsensusResult(
        agreement_score=0.85,
        consensus_points=[
            MockConsensusPoint("Use microservices architecture", ["system-architect", "backend-developer"], 1.0, "unanimous"),
            MockConsensusPoint("Implement API gateway", ["system-architect", "devops-engineer"], 0.67, "majority"),
            MockConsensusPoint("Use Kubernetes for orchestration", ["backend-developer", "devops-engineer"], 0.67, "majority")
        ],
        disagreement_points=[],
        dominant_themes=["microservices", "kubernetes", "scalability"],
        recommended_action="Strong consensus achieved. Proceed with recommendations.",
        confidence=0.88,
        metadata={"total_responses": 3}
    )

    # Synthesize
    synthesizer = ResponseSynthesizer()
    result = synthesizer.synthesize(
        query="Design a scalable microservices architecture",
        swarm_result=mock_swarm,
        consensus_result=mock_consensus,
        style="comprehensive"
    )

    print("\n" + "=" * 80)
    print("SYNTHESIZED RESPONSE")
    print("=" * 80)
    print(result.content)
    print("\n" + "=" * 80)
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Sources: {', '.join(result.sources)}")
    print(f"Key Recommendations: {len(result.key_recommendations)}")
