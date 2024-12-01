# WORK IN PROGESS COMMAND



import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from typing import List, Tuple, Dict
import asyncio
from collections import deque
import random

from utils.api import get_fame_n_wars_ago, get_current_clan_members, is_real_clan_tag
from discord import File

class FamePredictor(nn.Module):
    def __init__(self, max_seq_length=9):
        super(FamePredictor, self).__init__()
        self.max_seq_length = max_seq_length

        self.lstm = nn.LSTM(
            input_size=1,
            hidden_size=32,
            num_layers=1,
            batch_first=True
        )

        self.actor = nn.Sequential(
            nn.Linear(32, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )

        self.critic = nn.Sequential(
            nn.Linear(32, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )

    def forward(self, x, lengths):
        # Reshape input to (batch_size, seq_len, 1)
        x = x.unsqueeze(-1)

        # Pack the padded sequence
        packed_x = nn.utils.rnn.pack_padded_sequence(
            x, lengths.cpu(), batch_first=True, enforce_sorted=False
        )

        # Process through LSTM
        lstm_out, (hidden, _) = self.lstm(packed_x)

        # Use the final hidden state
        final_hidden = hidden[-1]

        # Get actor and critic outputs
        actor_output = self.actor(final_hidden)
        critic_output = self.critic(final_hidden)

        return actor_output, critic_output


class PPOMemory:
    def __init__(self):
        self.states = []
        self.lengths = []
        self.actions = []
        self.rewards = []
        self.values = []
        self.log_probs = []

    def clear(self):
        self.states.clear()
        self.lengths.clear()
        self.actions.clear()
        self.rewards.clear()
        self.values.clear()
        self.log_probs.clear()


class PPOTrainer:
    def __init__(self, learning_rate=0.0003, gamma=0.99, epsilon=0.2):
        self.model = FamePredictor()
        self.optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
        self.memory = PPOMemory()
        self.gamma = gamma
        self.epsilon = epsilon

    def normalize_fame_data(self, fame_data: List[float]) -> List[float]:
        if not fame_data:
            return []
        max_fame = max(fame_data)
        return [f / max_fame if max_fame > 0 else 0 for f in fame_data]

    def pad_sequence(self, sequence: List[float], max_length: int = 9) -> Tuple[List[float], int]:
        length = len(sequence)
        return sequence + [0] * (max_length - length), length


async def handle_train_ppo_command(interaction, clan_tags: str):
    await interaction.response.defer()

    progress_message = await interaction.followup.send("Initializing PPO training process...")

    try:
        clan_tag_list = clan_tags.split(',')

        await progress_message.edit(content="🔍 Validating clan tags...")
        for tag in clan_tag_list:
            if not await is_real_clan_tag(tag):
                await progress_message.edit(content=f"❌ Invalid clan tag: {tag}")
                return

        trainer = PPOTrainer()
        training_data = []

        # Collect training data
        await progress_message.edit(content="📊 Collecting historical fame data...")
        for clan_tag in clan_tag_list:
            await progress_message.edit(content=f"Processing clan {clan_tag}...")

            # Get current members
            clan_name, current_members = await get_current_clan_members(clan_tag)

            for member_tag, member_name in current_members:
                member_data = []

                # Get fame for each week from when they joined until 1 war ago
                for n in range(10, 1, -1):
                    fame = await get_fame_n_wars_ago(clan_tag, member_tag, n)
                    if fame is not None and fame != '0':
                        member_data.append(float(fame))

                if member_data:  # If we have any data points
                    # Get actual fame from 1 war ago as target
                    target_fame = float(await get_fame_n_wars_ago(clan_tag, member_tag, 1) or '0')
                    training_data.append((member_data, target_fame, clan_name, member_name))

                    await progress_message.edit(content=f"""
Processing clan {clan_tag}
Member: {member_name}
Historical fame points: {member_data}
Target fame (1 war ago): {target_fame}
Total training samples: {len(training_data)}
                    """.strip())

        if not training_data:
            await progress_message.edit(content="❌ No valid training data collected!")
            return

        # Training loop
        epochs = 1000
        batch_size = 64
        best_loss = float('inf')
        patience = 500
        patience_counter = 0

        await progress_message.edit(content="🧠 Starting PPO training...")

        for epoch in range(epochs):
            epoch_losses = []
            random.shuffle(training_data)

            for i in range(0, len(training_data), batch_size):
                batch = training_data[i:i + batch_size]

                # Prepare batch data with padding
                padded_states = []
                lengths = []
                targets = []

                for state, target, _, _ in batch:
                    padded_state, length = trainer.pad_sequence(state)
                    padded_states.append(padded_state)
                    lengths.append(length)
                    targets.append(target)

                batch_states = torch.tensor(padded_states, dtype=torch.float32)
                batch_lengths = torch.tensor(lengths, dtype=torch.long)
                batch_targets = torch.tensor(targets, dtype=torch.float32)

                # Get predictions and values
                with torch.no_grad():
                    old_predictions, old_values = trainer.model(batch_states, batch_lengths)

                # PPO update
                for _ in range(5):  # Multiple PPO iterations
                    predictions, values = trainer.model(batch_states, batch_lengths)

                    # Calculate advantages
                    advantages = batch_targets - values.detach()

                    # Calculate ratios and PPO loss
                    ratios = predictions / (old_predictions.detach() + 1e-8)
                    surr1 = ratios * advantages
                    surr2 = torch.clamp(ratios, 1 - trainer.epsilon, 1 + trainer.epsilon) * advantages
                    actor_loss = -torch.min(surr1, surr2).mean()

                    # Value loss
                    value_loss = nn.MSELoss()(values.squeeze(), batch_targets)

                    # Total loss
                    loss = actor_loss + 0.5 * value_loss

                    # Optimization step
                    trainer.optimizer.zero_grad()
                    loss.backward()
                    trainer.optimizer.step()

                    epoch_losses.append(loss.item())

            avg_loss = sum(epoch_losses) / len(epoch_losses)

            if avg_loss < best_loss:
                best_loss = avg_loss
                patience_counter = 0
                # Save best model
                torch.save(trainer.model.state_dict(), 'best_fame_predictor.pt')
            else:
                patience_counter += 1

            await progress_message.edit(content=f"""
Training Progress:
Epoch {epoch + 1}/{epochs}
Average Loss: {avg_loss:.4f}
Best Loss: {best_loss:.4f}
Patience Counter: {patience_counter}/{patience}
            """.strip())

            if patience_counter >= patience:
                break

        # Calculate top 5 best and worst predictions
        prediction_errors = []

        for state, target, clan_name, member_name in training_data:
            padded_state, length = trainer.pad_sequence(state)
            state_tensor = torch.tensor([padded_state], dtype=torch.float32)
            length_tensor = torch.tensor([length], dtype=torch.long)
            prediction, _ = trainer.model(state_tensor, length_tensor)
            error = abs(prediction.item() - target)
            prediction_errors.append((prediction.item(), target, error, clan_name, member_name))

        # Sort by error
        prediction_errors.sort(key=lambda x: x[2])
        best_predictions = prediction_errors[:5]
        worst_predictions = prediction_errors[-5:]

        best_predictions_str = "\n".join([
            f"Clan: {p[3]}, Member: {p[4]}, Predicted: {p[0]:.2f}, Actual: {p[1]:.2f}, Error: {p[2]:.2f}"
            for p in best_predictions
        ])
        worst_predictions_str = "\n".join([
            f"Clan: {p[3]}, Member: {p[4]}, Predicted: {p[0]:.2f}, Actual: {p[1]:.2f}, Error: {p[2]:.2f}"
            for p in worst_predictions
        ])

        await progress_message.edit(content=f"""
Training Complete! (Early stopping triggered)
Final Best Loss: {best_loss:.4f}
Model saved as 'best_fame_predictor.pt'

Top 5 Best Predictions:
{best_predictions_str}

Top 5 Worst Predictions:
{worst_predictions_str}
        """.strip())

        # Add a button to download the model
        with open('best_fame_predictor.pt', 'rb') as f:
            await interaction.followup.send(
                content="Download the trained model:",
                file=File(f, filename='best_fame_predictor.pt')
            )

    except Exception as e:
        await progress_message.edit(content=f"❌ An error occurred during training: {str(e)}")
        raise e