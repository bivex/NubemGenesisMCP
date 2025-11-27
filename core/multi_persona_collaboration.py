"""
Multi-Persona Collaboration - Orchestrate multiple personas working together
Enable collaborative problem-solving with specialized personas
"""

import logging
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncio

from core.personas_extended import get_persona, ALL_EXTENDED_PERSONAS
from core.persona_memory import get_persona_memory
from core.llm_integration import llm_handler as default_llm_handler

logger = logging.getLogger(__name__)


class CollaborationMode(Enum):
    """Collaboration modes"""
    SEQUENTIAL = "sequential"  # Each persona contributes in sequence
    PARALLEL = "parallel"  # All personas work simultaneously
    DEBATE = "debate"  # Personas discuss and reach consensus
    HIERARCHICAL = "hierarchical"  # Leader persona coordinates others
    SWARM = "swarm"  # Emergent collaboration


@dataclass
class PersonaContribution:
    """Contribution from a persona"""
    persona_key: str
    content: str
    confidence: float  # 0-1
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class CollaborationResult:
    """Result of multi-persona collaboration"""
    contributions: List[PersonaContribution]
    synthesis: str
    consensus_score: float  # 0-1, how much personas agree
    execution_time: float
    mode: CollaborationMode
    metadata: Dict[str, Any] = field(default_factory=dict)


class MultiPersonaCollaboration:
    """
    Orchestrate collaboration between multiple personas

    Features:
    - Multiple collaboration modes
    - Automatic persona selection based on task
    - Consensus building
    - Memory integration (each persona remembers collaboration)
    - Synthesis of multiple perspectives
    """

    def __init__(
        self,
        mode: CollaborationMode = CollaborationMode.SEQUENTIAL,
        max_personas: int = 5,
        memory_enabled: bool = True
    ):
        """
        Initialize Multi-Persona Collaboration

        Args:
            mode: Collaboration mode
            max_personas: Maximum personas in a collaboration
            memory_enabled: Enable memory for personas
        """
        self.mode = mode
        self.max_personas = max_personas
        self.memory_enabled = memory_enabled

    def select_personas(
        self,
        task: str,
        required_skills: Optional[List[str]] = None,
        num_personas: int = 3
    ) -> List[str]:
        """
        Automatically select best personas for a task

        Args:
            task: Task description
            required_skills: Required skills/specialties
            num_personas: Number of personas to select

        Returns:
            List of persona keys
        """
        # Score personas based on relevance
        scores = []

        for key, persona in ALL_EXTENDED_PERSONAS.items():
            score = 0.0

            # Check specialties match
            specialties = persona.get('specialties', [])
            if isinstance(specialties, list):
                specialty_text = ' '.join(str(s).lower() for s in specialties)

                # Simple keyword matching (could use embeddings for better results)
                task_lower = task.lower()
                for word in task_lower.split():
                    if len(word) > 3 and word in specialty_text:
                        score += 1.0

            # Bonus for required skills
            if required_skills:
                for skill in required_skills:
                    if any(skill.lower() in str(s).lower() for s in specialties):
                        score += 2.0

            # Bonus for Tier 1 personas
            if persona.get('tier') == 1:
                score += 0.5

            scores.append((key, score))

        # Sort by score and select top N
        scores.sort(key=lambda x: x[1], reverse=True)
        selected = [key for key, score in scores[:num_personas] if score > 0]

        logger.info(f"Selected personas for task: {selected}")
        return selected

    async def collaborate_sequential(
        self,
        task: str,
        persona_keys: List[str],
        llm_handler: Optional[Callable] = None
    ) -> CollaborationResult:
        """
        Sequential collaboration - each persona builds on previous contributions

        Args:
            task: Task description
            persona_keys: List of persona keys to involve
            llm_handler: Handler for LLM calls (async function)

        Returns:
            CollaborationResult
        """
        import time
        start_time = time.time()

        contributions = []
        context = f"Task: {task}\n\n"

        for i, persona_key in enumerate(persona_keys):
            logger.info(f"Getting contribution from {persona_key} ({i+1}/{len(persona_keys)})")

            # Get persona
            persona = get_persona(persona_key)
            if not persona:
                logger.warning(f"Persona {persona_key} not found")
                continue

            # Build prompt with context
            prompt = f"{context}\nYou are {persona['identity'].get('name', persona_key)}.\n"
            prompt += f"Your expertise: {', '.join(persona['specialties'][:5])}...\n\n"

            if i > 0:
                prompt += "Previous contributions:\n"
                for contrib in contributions[-2:]:  # Last 2 contributions for context
                    prompt += f"- {contrib.persona_key}: {contrib.content[:200]}...\n"

            prompt += f"\nProvide your perspective on: {task}"

            # Get contribution from LLM
            if llm_handler is None:
                llm_handler = default_llm_handler

            try:
                contribution_text = await llm_handler(prompt=prompt, persona_key=persona_key)
            except Exception as e:
                logger.error(f"Error getting contribution from {persona_key}: {e}")
                contribution_text = f"[Error from {persona_key}: {e}]"

            # Create contribution
            contribution = PersonaContribution(
                persona_key=persona_key,
                content=contribution_text,
                confidence=0.8,
                timestamp=time.time()
            )
            contributions.append(contribution)

            # Add to context
            context += f"\n{persona_key}: {contribution_text[:300]}...\n"

            # Store in memory
            if self.memory_enabled:
                memory = get_persona_memory(persona_key)
                memory.add_memory(
                    content=f"Collaborated on: {task}. My contribution: {contribution_text[:200]}",
                    memory_type='collaboration',
                    importance=0.7
                )

        # Synthesize contributions
        synthesis = self._synthesize_contributions(contributions, task)

        # Calculate consensus (simple version)
        consensus_score = min(1.0, len(contributions) / len(persona_keys))

        result = CollaborationResult(
            contributions=contributions,
            synthesis=synthesis,
            consensus_score=consensus_score,
            execution_time=time.time() - start_time,
            mode=CollaborationMode.SEQUENTIAL
        )

        logger.info(f"Sequential collaboration completed in {result.execution_time:.2f}s")
        return result

    async def collaborate_parallel(
        self,
        task: str,
        persona_keys: List[str],
        llm_handler: Optional[Callable] = None
    ) -> CollaborationResult:
        """
        Parallel collaboration - all personas work simultaneously

        Args:
            task: Task description
            persona_keys: List of persona keys
            llm_handler: Handler for LLM calls

        Returns:
            CollaborationResult
        """
        import time
        start_time = time.time()

        # Create tasks for each persona
        async def get_contribution(persona_key: str) -> PersonaContribution:
            persona = get_persona(persona_key)
            if not persona:
                return None

            prompt = f"Task: {task}\n\nYou are {persona['identity'].get('name', persona_key)}.\n"
            prompt += f"Expertise: {', '.join(persona['specialties'][:5])}...\n\n"
            prompt += f"Provide your analysis: {task}"

            if llm_handler is None:
                llm_handler = default_llm_handler

            try:
                content = await llm_handler(prompt=prompt, persona_key=persona_key)
            except Exception as e:
                logger.error(f"Error from {persona_key}: {e}")
                content = f"[Error from {persona_key}: {e}]"

            return PersonaContribution(
                persona_key=persona_key,
                content=content,
                confidence=0.8,
                timestamp=time.time()
            )

        # Execute all in parallel
        contribution_tasks = [get_contribution(key) for key in persona_keys]
        contributions = await asyncio.gather(*contribution_tasks)
        contributions = [c for c in contributions if c is not None]

        # Synthesize
        synthesis = self._synthesize_contributions(contributions, task)
        consensus_score = self._calculate_consensus(contributions)

        result = CollaborationResult(
            contributions=contributions,
            synthesis=synthesis,
            consensus_score=consensus_score,
            execution_time=time.time() - start_time,
            mode=CollaborationMode.PARALLEL
        )

        logger.info(f"Parallel collaboration completed in {result.execution_time:.2f}s")
        return result

    def _synthesize_contributions(
        self,
        contributions: List[PersonaContribution],
        task: str
    ) -> str:
        """
        Synthesize multiple contributions into a coherent response

        Args:
            contributions: List of persona contributions
            task: Original task

        Returns:
            Synthesized response
        """
        if not contributions:
            return "No contributions available."

        synthesis_parts = [f"Collaborative Analysis of: {task}\n"]
        synthesis_parts.append(f"\n{len(contributions)} expert perspectives:\n")

        for i, contrib in enumerate(contributions, 1):
            persona = get_persona(contrib.persona_key)
            name = persona['identity'].get('name', contrib.persona_key) if persona else contrib.persona_key

            synthesis_parts.append(f"\n{i}. {name}:")
            synthesis_parts.append(f"   {contrib.content[:300]}...")

        synthesis_parts.append("\n\nKey Insights:")
        synthesis_parts.append("- Multiple expert perspectives considered")
        synthesis_parts.append(f"- Consensus score: {self._calculate_consensus(contributions):.0%}")
        synthesis_parts.append("- Collaborative approach ensures comprehensive analysis")

        return "\n".join(synthesis_parts)

    def _calculate_consensus(self, contributions: List[PersonaContribution]) -> float:
        """
        Calculate consensus score between contributions

        Args:
            contributions: List of contributions

        Returns:
            Consensus score (0-1)
        """
        if len(contributions) < 2:
            return 1.0

        # Simple heuristic: average confidence
        avg_confidence = sum(c.confidence for c in contributions) / len(contributions)

        # Adjust based on number of contributors
        contributor_factor = min(1.0, len(contributions) / self.max_personas)

        return avg_confidence * contributor_factor

    async def collaborate_debate(
        self,
        task: str,
        persona_keys: List[str],
        llm_handler: Optional[Callable] = None,
        rounds: int = 3
    ) -> CollaborationResult:
        """
        Debate collaboration - personas discuss and refine ideas through multiple rounds

        Args:
            task: Task description
            persona_keys: List of persona keys
            llm_handler: Handler for LLM calls
            rounds: Number of debate rounds

        Returns:
            CollaborationResult
        """
        import time
        start_time = time.time()

        if llm_handler is None:
            llm_handler = default_llm_handler

        all_contributions = []
        debate_history = []

        for round_num in range(rounds):
            logger.info(f"Debate round {round_num + 1}/{rounds}")

            round_contributions = []

            for persona_key in persona_keys:
                persona = get_persona(persona_key)
                if not persona:
                    continue

                # Build debate context
                prompt = f"DEBATE ROUND {round_num + 1}/{rounds}\n\n"
                prompt += f"Task: {task}\n\n"
                prompt += f"You are {persona['identity'].get('name', persona_key)}.\n"
                prompt += f"Expertise: {', '.join(persona['specialties'][:5])}...\n\n"

                if debate_history:
                    prompt += "Previous arguments:\n"
                    for prev_round in debate_history[-2:]:  # Last 2 rounds
                        for contrib in prev_round:
                            prompt += f"- {contrib.persona_key}: {contrib.content[:150]}...\n"
                    prompt += "\n"

                if round_num == 0:
                    prompt += "Present your initial perspective and key arguments."
                elif round_num < rounds - 1:
                    prompt += "Respond to other perspectives. Refine your arguments or find common ground."
                else:
                    prompt += "Final synthesis: What's the best path forward considering all perspectives?"

                try:
                    content = await llm_handler(prompt=prompt, persona_key=persona_key)
                except Exception as e:
                    logger.error(f"Error from {persona_key} in round {round_num + 1}: {e}")
                    content = f"[Error: {e}]"

                contribution = PersonaContribution(
                    persona_key=persona_key,
                    content=content,
                    confidence=0.7 + (round_num * 0.1),  # Confidence increases with rounds
                    timestamp=time.time(),
                    metadata={'round': round_num + 1}
                )

                round_contributions.append(contribution)
                all_contributions.append(contribution)

            debate_history.append(round_contributions)

        # Final synthesis emphasizing debate process
        synthesis_parts = [f"Debate Resolution: {task}\n"]
        synthesis_parts.append(f"\n{rounds} rounds of debate with {len(persona_keys)} experts:\n")

        for round_num, round_contribs in enumerate(debate_history, 1):
            synthesis_parts.append(f"\nRound {round_num}:")
            for contrib in round_contribs:
                persona = get_persona(contrib.persona_key)
                name = persona['identity'].get('name', contrib.persona_key) if persona else contrib.persona_key
                synthesis_parts.append(f"  {name}: {contrib.content[:200]}...")

        synthesis_parts.append(f"\n\nDebate Outcome:")
        synthesis_parts.append("- Multiple perspectives thoroughly explored")
        synthesis_parts.append("- Arguments refined through {rounds} rounds of discussion")
        synthesis_parts.append(f"- Final consensus score: {self._calculate_consensus(all_contributions):.0%}")

        synthesis = "\n".join(synthesis_parts)

        result = CollaborationResult(
            contributions=all_contributions,
            synthesis=synthesis,
            consensus_score=self._calculate_consensus(all_contributions),
            execution_time=time.time() - start_time,
            mode=CollaborationMode.DEBATE,
            metadata={'rounds': rounds, 'participants': len(persona_keys)}
        )

        logger.info(f"Debate collaboration completed in {result.execution_time:.2f}s")
        return result

    async def collaborate_hierarchical(
        self,
        task: str,
        persona_keys: List[str],
        llm_handler: Optional[Callable] = None,
        leader_key: Optional[str] = None
    ) -> CollaborationResult:
        """
        Hierarchical collaboration - leader persona coordinates team

        Args:
            task: Task description
            persona_keys: List of persona keys (first one is leader if leader_key not specified)
            llm_handler: Handler for LLM calls
            leader_key: Optional specific leader persona

        Returns:
            CollaborationResult
        """
        import time
        start_time = time.time()

        if llm_handler is None:
            llm_handler = default_llm_handler

        # Determine leader
        if leader_key and leader_key in persona_keys:
            leader = leader_key
            team = [k for k in persona_keys if k != leader_key]
        else:
            leader = persona_keys[0]
            team = persona_keys[1:]

        logger.info(f"Hierarchical collaboration: Leader={leader}, Team={team}")

        contributions = []

        # Phase 1: Leader breaks down task
        logger.info("Phase 1: Leader analysis and task breakdown")
        leader_persona = get_persona(leader)
        if leader_persona:
            prompt = f"You are the team leader: {leader_persona['identity'].get('name', leader)}.\n\n"
            prompt += f"Task: {task}\n\n"
            prompt += f"Team members available: {', '.join(team)}\n\n"
            prompt += "As leader, provide:\n"
            prompt += "1. Your analysis of the task\n"
            prompt += "2. Key subtasks to delegate\n"
            prompt += "3. Coordination strategy"

            try:
                leader_analysis = await llm_handler(prompt=prompt, persona_key=leader)
            except Exception as e:
                logger.error(f"Error from leader {leader}: {e}")
                leader_analysis = f"[Error: {e}]"

            contributions.append(PersonaContribution(
                persona_key=leader,
                content=leader_analysis,
                confidence=0.9,
                timestamp=time.time(),
                metadata={'role': 'leader', 'phase': 'analysis'}
            ))

        # Phase 2: Team members contribute
        logger.info("Phase 2: Team member contributions")
        for team_member in team:
            persona = get_persona(team_member)
            if not persona:
                continue

            prompt = f"You are: {persona['identity'].get('name', team_member)}.\n"
            prompt += f"Expertise: {', '.join(persona['specialties'][:5])}...\n\n"
            prompt += f"Task: {task}\n\n"
            prompt += f"Leader's analysis:\n{leader_analysis[:300]}...\n\n"
            prompt += "Provide your specialized contribution to the team effort."

            try:
                content = await llm_handler(prompt=prompt, persona_key=team_member)
            except Exception as e:
                logger.error(f"Error from team member {team_member}: {e}")
                content = f"[Error: {e}]"

            contributions.append(PersonaContribution(
                persona_key=team_member,
                content=content,
                confidence=0.8,
                timestamp=time.time(),
                metadata={'role': 'team_member', 'phase': 'contribution'}
            ))

        # Phase 3: Leader synthesis
        logger.info("Phase 3: Leader synthesis")
        if leader_persona:
            team_inputs = "\n\n".join([
                f"{c.persona_key}: {c.content[:200]}..."
                for c in contributions[1:]  # Skip leader's initial analysis
            ])

            prompt = f"As team leader ({leader}), synthesize the team's contributions:\n\n"
            prompt += f"Task: {task}\n\n"
            prompt += f"Team contributions:\n{team_inputs}\n\n"
            prompt += "Provide final synthesis and recommendations."

            try:
                final_synthesis = await llm_handler(prompt=prompt, persona_key=leader)
            except Exception as e:
                logger.error(f"Error from leader synthesis: {e}")
                final_synthesis = f"[Error: {e}]"

            contributions.append(PersonaContribution(
                persona_key=leader,
                content=final_synthesis,
                confidence=0.95,
                timestamp=time.time(),
                metadata={'role': 'leader', 'phase': 'synthesis'}
            ))

        # Build synthesis
        synthesis_parts = [f"Hierarchical Collaboration: {task}\n"]
        synthesis_parts.append(f"\nLeader: {leader}")
        synthesis_parts.append(f"Team: {', '.join(team)}\n")
        synthesis_parts.append(f"\nLeader Analysis:\n{contributions[0].content[:300]}...\n")
        synthesis_parts.append(f"\nTeam Contributions: {len(team)} specialists")
        synthesis_parts.append(f"\nFinal Synthesis:\n{final_synthesis[:400]}...")

        synthesis = "\n".join(synthesis_parts)

        result = CollaborationResult(
            contributions=contributions,
            synthesis=synthesis,
            consensus_score=0.9,  # High consensus in hierarchical mode
            execution_time=time.time() - start_time,
            mode=CollaborationMode.HIERARCHICAL,
            metadata={'leader': leader, 'team_size': len(team)}
        )

        logger.info(f"Hierarchical collaboration completed in {result.execution_time:.2f}s")
        return result

    async def collaborate_swarm(
        self,
        task: str,
        persona_keys: Optional[List[str]] = None,
        num_personas: int = 5,
        max_iterations: int = 3,
        convergence_threshold: float = 0.8,
        llm_handler: Optional[Callable] = None
    ) -> CollaborationResult:
        """
        Swarm collaboration - Emergent, self-organizing collaboration

        In swarm mode:
        1. All personas start with initial perspectives
        2. Each iteration, personas:
           - See summaries of others' contributions
           - Can refine their own perspective
           - Can vote on/endorse others' ideas
        3. System tracks emerging consensus
        4. Stops when convergence reached or max iterations

        Args:
            task: Task to collaborate on
            persona_keys: Optional list of persona keys
            num_personas: Number of personas
            max_iterations: Maximum swarm iterations
            convergence_threshold: Stop when consensus reaches this
            llm_handler: Async LLM handler

        Returns:
            CollaborationResult
        """
        start_time = time.time()

        if llm_handler is None:
            llm_handler = default_llm_handler

        # Select personas
        if not persona_keys:
            persona_keys = self._select_best_personas(task, num_personas)

        logger.info(f"Starting swarm collaboration with {len(persona_keys)} personas")

        # Swarm state
        contributions: List[PersonaContribution] = []
        persona_states: Dict[str, Dict[str, Any]] = {}

        # Initialize persona states
        for pk in persona_keys:
            persona_states[pk] = {
                'current_perspective': None,
                'endorsements': [],  # Ideas they endorse
                'iterations': 0
            }

        # Swarm iterations
        for iteration in range(max_iterations):
            logger.info(f"Swarm iteration {iteration + 1}/{max_iterations}")

            # All personas contribute in parallel
            iteration_tasks = []

            for persona_key in persona_keys:
                state = persona_states[persona_key]

                # Build context: see others' latest perspectives
                other_perspectives = []
                for other_pk, other_state in persona_states.items():
                    if other_pk != persona_key and other_state['current_perspective']:
                        other_perspectives.append({
                            'persona': other_pk,
                            'perspective': other_state['current_perspective'][:200]
                        })

                # Build prompt
                if iteration == 0:
                    # Initial perspective
                    prompt = f"Task: {task}\n\n"
                    prompt += "Provide your initial perspective and key insights (be concise, 2-3 sentences)."
                else:
                    # Iterative refinement
                    prompt = f"Task: {task}\n\n"
                    prompt += f"Your previous perspective:\n{state['current_perspective'][:200]}...\n\n"

                    if other_perspectives:
                        prompt += "Other personas' perspectives:\n"
                        for op in other_perspectives[:3]:
                            prompt += f"- [{op['persona']}] {op['perspective']}...\n"
                        prompt += "\n"

                    prompt += "Refine your perspective considering others' views, or endorse another's idea. "
                    prompt += "Start with [ENDORSE: persona_key] if you fully agree with another."

                iteration_tasks.append(
                    self._swarm_persona_iteration(
                        persona_key, prompt, llm_handler, iteration
                    )
                )

            # Execute iteration in parallel
            iteration_results = await asyncio.gather(*iteration_tasks, return_exceptions=True)

            # Process results
            for persona_key, result in zip(persona_keys, iteration_results):
                if isinstance(result, Exception):
                    logger.error(f"Error from {persona_key} in iteration {iteration}: {result}")
                    continue

                content, confidence = result

                # Check for endorsement
                endorsement_match = None
                if content.startswith('[ENDORSE:'):
                    try:
                        endorsed = content.split('[ENDORSE:')[1].split(']')[0].strip()
                        endorsement_match = endorsed
                        persona_states[persona_key]['endorsements'].append(endorsed)
                        logger.info(f"{persona_key} endorses {endorsed}")
                    except:
                        pass

                # Update state
                persona_states[persona_key]['current_perspective'] = content
                persona_states[persona_key]['iterations'] += 1

                # Add contribution
                contributions.append(PersonaContribution(
                    persona_key=persona_key,
                    content=content,
                    confidence=confidence,
                    timestamp=time.time(),
                    metadata={
                        'iteration': iteration,
                        'endorsement': endorsement_match
                    }
                ))

            # Calculate convergence
            endorsement_graph = self._build_endorsement_graph(persona_states)
            convergence = self._calculate_convergence(endorsement_graph, len(persona_keys))

            logger.info(f"Iteration {iteration + 1} convergence: {convergence:.2%}")

            # Check convergence
            if convergence >= convergence_threshold:
                logger.info(f"Swarm converged at iteration {iteration + 1}")
                break

        # Identify emergent consensus
        dominant_perspectives = self._identify_dominant_perspectives(persona_states)

        # Build synthesis
        synthesis_parts = [f"Swarm Collaboration: {task}\n"]
        synthesis_parts.append(f"\nSwarm size: {len(persona_keys)}")
        synthesis_parts.append(f"Iterations: {iteration + 1}")
        synthesis_parts.append(f"Final convergence: {convergence:.2%}\n")

        synthesis_parts.append("\nEmergent Consensus:")
        for perspective_cluster in dominant_perspectives[:3]:
            personas = ', '.join(perspective_cluster['personas'])
            synthesis_parts.append(f"\n[Cluster {len(perspective_cluster['personas'])} personas: {personas}]")
            synthesis_parts.append(perspective_cluster['representative_view'][:300] + "...")

        synthesis = "\n".join(synthesis_parts)

        result = CollaborationResult(
            contributions=contributions,
            synthesis=synthesis,
            consensus_score=convergence,
            execution_time=time.time() - start_time,
            mode=CollaborationMode.SWARM,
            metadata={
                'iterations': iteration + 1,
                'final_convergence': convergence,
                'clusters': len(dominant_perspectives)
            }
        )

        logger.info(f"Swarm collaboration completed in {result.execution_time:.2f}s")
        return result

    async def _swarm_persona_iteration(
        self,
        persona_key: str,
        prompt: str,
        llm_handler: Callable,
        iteration: int
    ) -> tuple[str, float]:
        """Execute one persona's iteration in swarm"""
        try:
            content = await llm_handler(prompt=prompt, persona_key=persona_key)

            # Calculate confidence (decreases with iterations)
            confidence = 0.9 - (iteration * 0.1)

            return (content, confidence)

        except Exception as e:
            logger.error(f"Error in swarm iteration for {persona_key}: {e}")
            return (f"[Error: {e}]", 0.5)

    def _build_endorsement_graph(
        self,
        persona_states: Dict[str, Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Build endorsement graph showing who endorses whom"""
        graph = {}

        for persona_key, state in persona_states.items():
            graph[persona_key] = state['endorsements']

        return graph

    def _calculate_convergence(
        self,
        endorsement_graph: Dict[str, List[str]],
        total_personas: int
    ) -> float:
        """
        Calculate swarm convergence (0-1)

        Convergence indicators:
        - Number of endorsements
        - Clustering of endorsements
        """
        if total_personas <= 1:
            return 1.0

        # Count total endorsements
        total_endorsements = sum(len(endorsements) for endorsements in endorsement_graph.values())

        # Maximum possible endorsements (each persona endorses one other)
        max_endorsements = total_personas

        # Base convergence from endorsement rate
        endorsement_rate = min(total_endorsements / max_endorsements, 1.0) if max_endorsements > 0 else 0.0

        # Clustering bonus: if endorsements concentrate on few personas
        endorsed_personas = set()
        for endorsements in endorsement_graph.values():
            endorsed_personas.update(endorsements)

        clustering_factor = 1.0 - (len(endorsed_personas) / max(total_personas, 1))

        # Combined convergence
        convergence = (endorsement_rate * 0.7) + (clustering_factor * 0.3)

        return min(convergence, 1.0)

    def _identify_dominant_perspectives(
        self,
        persona_states: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Identify clusters of similar perspectives

        Returns list of clusters with:
        - personas: list of persona keys
        - representative_view: the perspective
        """
        clusters = []

        # Group by endorsements
        endorsement_groups: Dict[str, List[str]] = {}

        for persona_key, state in persona_states.items():
            endorsements = state['endorsements']

            if not endorsements:
                # Independent perspective
                clusters.append({
                    'personas': [persona_key],
                    'representative_view': state['current_perspective'] or "No perspective"
                })
            else:
                # Endorsed someone
                endorsed = endorsements[0]  # Take first endorsement
                if endorsed not in endorsement_groups:
                    endorsement_groups[endorsed] = []
                endorsement_groups[endorsed].append(persona_key)

        # Create clusters from endorsement groups
        for endorsed_persona, endorsers in endorsement_groups.items():
            cluster_personas = [endorsed_persona] + endorsers
            representative = persona_states[endorsed_persona]['current_perspective'] or "No perspective"

            clusters.append({
                'personas': cluster_personas,
                'representative_view': representative
            })

        # Sort by cluster size
        clusters.sort(key=lambda c: len(c['personas']), reverse=True)

        return clusters

    async def collaborate(
        self,
        task: str,
        persona_keys: Optional[List[str]] = None,
        num_personas: int = 3,
        llm_handler: Optional[Callable] = None
    ) -> CollaborationResult:
        """
        Main collaboration method - uses configured mode

        Args:
            task: Task description
            persona_keys: Specific personas to use, or None for auto-selection
            num_personas: Number of personas if auto-selecting
            llm_handler: Handler for LLM calls

        Returns:
            CollaborationResult
        """
        # Select personas if not provided
        if not persona_keys:
            persona_keys = self.select_personas(task, num_personas=num_personas)

        if not persona_keys:
            raise ValueError("No personas available for collaboration")

        # Limit to max personas
        persona_keys = persona_keys[:self.max_personas]

        logger.info(f"Starting {self.mode.value} collaboration with {len(persona_keys)} personas")

        # Execute based on mode
        if self.mode == CollaborationMode.SEQUENTIAL:
            return await self.collaborate_sequential(task, persona_keys, llm_handler)
        elif self.mode == CollaborationMode.PARALLEL:
            return await self.collaborate_parallel(task, persona_keys, llm_handler)
        elif self.mode == CollaborationMode.DEBATE:
            return await self.collaborate_debate(task, persona_keys, llm_handler)
        elif self.mode == CollaborationMode.HIERARCHICAL:
            return await self.collaborate_hierarchical(task, persona_keys, llm_handler)
        elif self.mode == CollaborationMode.SWARM:
            return await self.collaborate_swarm(task, persona_keys, num_personas, llm_handler=llm_handler)
        else:
            # Default to sequential
            return await self.collaborate_sequential(task, persona_keys, llm_handler)


if __name__ == "__main__":
    # Test multi-persona collaboration
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*60)
    print("Testing Multi-Persona Collaboration")
    print("="*60 + "\n")

    # Create collaboration system
    collab = MultiPersonaCollaboration(
        mode=CollaborationMode.SEQUENTIAL,
        max_personas=3
    )

    # Test task
    task = "Design a scalable microservices architecture for an e-commerce platform"

    print(f"Task: {task}\n")

    # Auto-select personas
    print("Auto-selecting personas...")
    selected = collab.select_personas(task, num_personas=3)
    print(f"Selected: {selected}\n")

    # Run collaboration (mock mode without LLM)
    print("Running sequential collaboration (mock mode)...")

    async def test_collaboration():
        result = await collab.collaborate(
            task=task,
            persona_keys=selected[:3]  # Use first 3
        )

        print(f"\nCollaboration completed in {result.execution_time:.2f}s")
        print(f"Contributions: {len(result.contributions)}")
        print(f"Consensus: {result.consensus_score:.0%}")
        print(f"\nSynthesis:")
        print(result.synthesis)

    # Run async test
    asyncio.run(test_collaboration())
