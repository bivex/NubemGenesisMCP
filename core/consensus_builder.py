#!/usr/bin/env python3
"""
Consensus Builder - Builds consensus from multiple persona responses
Analyzes agreement, identifies key points, and determines confidence
"""

import re
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from collections import Counter, defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConsensusPoint:
    """A point of consensus among personas"""
    content: str
    supporting_personas: List[str]
    confidence: float
    category: str  # "unanimous", "majority", "minority"


@dataclass
class DisagreementPoint:
    """A point of disagreement among personas"""
    topic: str
    opinions: Dict[str, str]  # persona -> opinion
    severity: str  # "minor", "moderate", "major"


@dataclass
class ConsensusResult:
    """Result of consensus building"""
    agreement_score: float  # 0-1, how much personas agree
    consensus_points: List[ConsensusPoint]
    disagreement_points: List[DisagreementPoint]
    dominant_themes: List[str]
    recommended_action: str
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConsensusBuilder:
    """
    Consensus Builder - Analyzes multiple persona responses to find agreement

    Methods:
    - Semantic similarity analysis
    - Key point extraction
    - Agreement scoring
    - Confidence calculation
    """

    # Keywords for identifying key concepts
    ACTION_KEYWORDS = [
        "should", "must", "need to", "recommend", "suggest",
        "important", "critical", "essential", "required"
    ]

    NEGATIVE_KEYWORDS = [
        "don't", "shouldn't", "avoid", "never", "not recommended",
        "risky", "dangerous", "problematic"
    ]

    def __init__(self, similarity_threshold: float = 0.7):
        """
        Initialize Consensus Builder

        Args:
            similarity_threshold: Minimum similarity to consider agreement (0-1)
        """
        self.similarity_threshold = similarity_threshold
        self.consensus_cache = {}

    def build_consensus(
        self,
        responses: List[Dict[str, Any]],
        query: str = ""
    ) -> ConsensusResult:
        """
        Build consensus from multiple persona responses

        Args:
            responses: List of persona responses (PersonaResponse objects or dicts)
            query: Original query for context

        Returns:
            ConsensusResult with consensus analysis
        """
        logger.info(f"🤝 Building consensus from {len(responses)} responses")

        if not responses:
            return self._empty_consensus()

        # Extract response texts
        response_texts = self._extract_texts(responses)
        persona_names = self._extract_personas(responses)

        # 1. Extract key points from each response
        all_key_points = self._extract_key_points(response_texts, persona_names)

        # 2. Find consensus points (what personas agree on)
        consensus_points = self._find_consensus_points(all_key_points, persona_names)

        # 3. Identify disagreements
        disagreement_points = self._find_disagreements(all_key_points, persona_names)

        # 4. Calculate agreement score
        agreement_score = self._calculate_agreement_score(consensus_points, disagreement_points, len(responses))

        # 5. Extract dominant themes
        dominant_themes = self._extract_dominant_themes(response_texts)

        # 6. Determine recommended action
        recommended_action = self._determine_recommendation(consensus_points, disagreement_points)

        # 7. Calculate overall confidence
        confidence = self._calculate_confidence(agreement_score, len(responses), consensus_points)

        result = ConsensusResult(
            agreement_score=agreement_score,
            consensus_points=consensus_points,
            disagreement_points=disagreement_points,
            dominant_themes=dominant_themes,
            recommended_action=recommended_action,
            confidence=confidence,
            metadata={
                "total_responses": len(responses),
                "successful_responses": sum(1 for r in responses if r.get("success", True)),
                "query": query
            }
        )

        logger.info(f"✅ Consensus built: agreement={agreement_score:.2f}, confidence={confidence:.2f}")

        return result

    def _extract_texts(self, responses: List[Dict[str, Any]]) -> List[str]:
        """Extract response texts from response objects"""
        texts = []
        for r in responses:
            if isinstance(r, dict):
                texts.append(r.get("response", ""))
            else:
                texts.append(getattr(r, "response", ""))
        return texts

    def _extract_personas(self, responses: List[Dict[str, Any]]) -> List[str]:
        """Extract persona names from response objects"""
        names = []
        for r in responses:
            if isinstance(r, dict):
                names.append(r.get("persona_name", "unknown"))
            else:
                names.append(getattr(r, "persona_name", "unknown"))
        return names

    def _extract_key_points(
        self,
        response_texts: List[str],
        persona_names: List[str]
    ) -> Dict[str, List[str]]:
        """
        Extract key points from each response

        Returns:
            Dict mapping persona_name -> list of key points
        """
        key_points = {}

        for persona, text in zip(persona_names, response_texts):
            points = []

            # Split into sentences
            sentences = re.split(r'[.!?]+', text)

            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                # Check if sentence contains action keywords
                if any(keyword in sentence.lower() for keyword in self.ACTION_KEYWORDS):
                    points.append(sentence)

                # Check for negative/warning keywords
                elif any(keyword in sentence.lower() for keyword in self.NEGATIVE_KEYWORDS):
                    points.append(sentence)

                # Include sentences that are important (heuristic: mentions specific tech/concepts)
                elif self._is_important_sentence(sentence):
                    points.append(sentence)

            key_points[persona] = points[:5]  # Top 5 key points per persona

        return key_points

    def _is_important_sentence(self, sentence: str) -> bool:
        """Heuristic to determine if sentence is important"""
        # Sentences with specific technical terms, numbers, or structure
        has_technical_term = bool(re.search(r'\b(API|database|server|cloud|security|architecture|performance)\b', sentence, re.IGNORECASE))
        has_number = bool(re.search(r'\d+', sentence))
        is_detailed = len(sentence.split()) > 10

        return has_technical_term or (has_number and is_detailed)

    def _find_consensus_points(
        self,
        all_key_points: Dict[str, List[str]],
        persona_names: List[str]
    ) -> List[ConsensusPoint]:
        """Find points where personas agree"""
        consensus_points = []

        # Extract all unique points
        all_points = []
        for persona, points in all_key_points.items():
            for point in points:
                all_points.append((persona, point.lower()))

        # Find similar points across personas
        point_clusters = self._cluster_similar_points(all_points)

        # Convert clusters to consensus points
        for cluster in point_clusters:
            personas_in_cluster = [p for p, _ in cluster]
            representative_point = cluster[0][1]  # Use first point as representative

            # Determine category
            agreement_ratio = len(personas_in_cluster) / len(persona_names)
            if agreement_ratio >= 0.9:
                category = "unanimous"
            elif agreement_ratio >= 0.6:
                category = "majority"
            else:
                category = "minority"

            # Only include majority or unanimous points
            if category in ["unanimous", "majority"]:
                consensus_points.append(
                    ConsensusPoint(
                        content=representative_point.capitalize(),
                        supporting_personas=personas_in_cluster,
                        confidence=agreement_ratio,
                        category=category
                    )
                )

        # Sort by confidence
        consensus_points.sort(key=lambda x: x.confidence, reverse=True)

        return consensus_points[:10]  # Top 10 consensus points

    def _cluster_similar_points(
        self,
        points: List[Tuple[str, str]]
    ) -> List[List[Tuple[str, str]]]:
        """Cluster similar points using simple word overlap"""
        clusters = []
        used_indices = set()

        for i, (persona1, point1) in enumerate(points):
            if i in used_indices:
                continue

            # Start new cluster
            cluster = [(persona1, point1)]
            used_indices.add(i)

            # Find similar points
            words1 = set(point1.lower().split())

            for j, (persona2, point2) in enumerate(points):
                if j in used_indices or j == i:
                    continue

                # Calculate word overlap
                words2 = set(point2.lower().split())
                overlap = len(words1 & words2) / max(len(words1), len(words2))

                if overlap >= self.similarity_threshold:
                    cluster.append((persona2, point2))
                    used_indices.add(j)

            # Only add clusters with multiple personas
            if len(cluster) > 1:
                clusters.append(cluster)

        return clusters

    def _find_disagreements(
        self,
        all_key_points: Dict[str, List[str]],
        persona_names: List[str]
    ) -> List[DisagreementPoint]:
        """Identify points of disagreement"""
        disagreements = []

        # Look for contradictory statements
        # This is simplified - in production would use more sophisticated analysis

        # For now, just identify when personas mention same concept differently
        concept_mentions = defaultdict(dict)

        for persona, points in all_key_points.items():
            for point in points:
                # Extract key concepts (simple heuristic)
                words = point.lower().split()
                for word in words:
                    if len(word) > 5:  # Only longer words (likely concepts)
                        concept_mentions[word][persona] = point

        # Find concepts mentioned by multiple personas
        for concept, persona_opinions in concept_mentions.items():
            if len(persona_opinions) >= 2:
                # Check if opinions differ
                unique_opinions = set(persona_opinions.values())
                if len(unique_opinions) > 1:
                    disagreements.append(
                        DisagreementPoint(
                            topic=concept,
                            opinions=persona_opinions,
                            severity="moderate"  # Simplified
                        )
                    )

        return disagreements[:5]  # Top 5 disagreements

    def _calculate_agreement_score(
        self,
        consensus_points: List[ConsensusPoint],
        disagreement_points: List[DisagreementPoint],
        total_responses: int
    ) -> float:
        """Calculate overall agreement score (0-1)"""
        if not consensus_points and not disagreement_points:
            return 0.5  # Neutral if no data

        # Weight consensus points positively
        consensus_weight = sum(cp.confidence for cp in consensus_points) / max(len(consensus_points), 1)

        # Weight disagreements negatively
        disagreement_weight = len(disagreement_points) * 0.1

        # Calculate score
        score = consensus_weight - disagreement_weight

        return min(max(score, 0.0), 1.0)

    def _extract_dominant_themes(self, response_texts: List[str]) -> List[str]:
        """Extract dominant themes from all responses"""
        # Combine all texts
        combined_text = " ".join(response_texts).lower()

        # Extract common technical terms
        words = re.findall(r'\b\w{5,}\b', combined_text)  # Words with 5+ chars

        # Count occurrences
        word_counts = Counter(words)

        # Filter for relevant terms (simple heuristic)
        technical_terms = {
            word: count for word, count in word_counts.items()
            if count >= 2  # Mentioned by at least 2 responses
            and word not in ["should", "would", "could", "about", "there", "their"]
        }

        # Get top themes
        dominant = sorted(technical_terms.items(), key=lambda x: x[1], reverse=True)

        return [word for word, count in dominant[:5]]

    def _determine_recommendation(
        self,
        consensus_points: List[ConsensusPoint],
        disagreement_points: List[DisagreementPoint]
    ) -> str:
        """Determine recommended action based on consensus"""
        if not consensus_points:
            return "Insufficient consensus for recommendation. Consider additional analysis."

        # Count unanimous vs majority
        unanimous = sum(1 for cp in consensus_points if cp.category == "unanimous")
        majority = sum(1 for cp in consensus_points if cp.category == "majority")

        if unanimous >= 3:
            return "Strong consensus achieved. Proceed with unanimous recommendations."
        elif unanimous + majority >= 5:
            return "Good consensus achieved. Review majority points and proceed carefully."
        elif disagreement_points:
            return "Partial consensus with notable disagreements. Further review recommended."
        else:
            return "Moderate consensus. Consider additional perspectives."

    def _calculate_confidence(
        self,
        agreement_score: float,
        num_responses: int,
        consensus_points: List[ConsensusPoint]
    ) -> float:
        """Calculate overall confidence in consensus"""
        # Base confidence from agreement score
        confidence = agreement_score

        # Boost for more responses
        if num_responses >= 5:
            confidence *= 1.1
        elif num_responses >= 3:
            confidence *= 1.05

        # Boost for unanimous consensus points
        unanimous_count = sum(1 for cp in consensus_points if cp.category == "unanimous")
        if unanimous_count >= 2:
            confidence *= 1.1

        return min(confidence, 1.0)

    def _empty_consensus(self) -> ConsensusResult:
        """Return empty consensus result"""
        return ConsensusResult(
            agreement_score=0.0,
            consensus_points=[],
            disagreement_points=[],
            dominant_themes=[],
            recommended_action="No responses to analyze",
            confidence=0.0
        )


# Convenience function
def build_consensus(
    responses: List[Dict[str, Any]],
    query: str = ""
) -> ConsensusResult:
    """Build consensus (convenience function)"""
    builder = ConsensusBuilder()
    return builder.build_consensus(responses, query)


if __name__ == "__main__":
    # Test Consensus Builder
    print("=" * 80)
    print("CONSENSUS BUILDER TEST")
    print("=" * 80)

    # Simulated responses
    test_responses = [
        {
            "persona_name": "system-architect",
            "response": "I recommend using microservices architecture. The system should be scalable and use API gateway. Consider using Kubernetes for orchestration.",
            "success": True
        },
        {
            "persona_name": "backend-developer",
            "response": "Microservices are essential for scalability. API gateway is critical. We should use containerization with Docker and Kubernetes.",
            "success": True
        },
        {
            "persona_name": "devops-engineer",
            "response": "Kubernetes is the best choice for container orchestration. Ensure scalability with horizontal pod autoscaling. API gateway will help manage traffic.",
            "success": True
        },
        {
            "persona_name": "security-expert",
            "response": "Security should be a priority. Use API gateway for authentication. Consider service mesh for security between microservices. Kubernetes has security features.",
            "success": True
        }
    ]

    builder = ConsensusBuilder()
    result = builder.build_consensus(test_responses, "Design a scalable system")

    print(f"\n📊 Agreement Score: {result.agreement_score:.2f}")
    print(f"🎯 Confidence: {result.confidence:.2f}")
    print(f"💡 Recommendation: {result.recommended_action}")

    print(f"\n✅ Consensus Points ({len(result.consensus_points)}):")
    for i, point in enumerate(result.consensus_points, 1):
        print(f"   {i}. [{point.category.upper()}] {point.content}")
        print(f"      Supporting: {', '.join(point.supporting_personas)}")
        print(f"      Confidence: {point.confidence:.2f}")

    print(f"\n🔍 Dominant Themes:")
    for theme in result.dominant_themes:
        print(f"   - {theme}")

    if result.disagreement_points:
        print(f"\n⚠️  Disagreements ({len(result.disagreement_points)}):")
        for disagreement in result.disagreement_points:
            print(f"   Topic: {disagreement.topic}")
            for persona, opinion in disagreement.opinions.items():
                print(f"      {persona}: {opinion[:80]}...")
