from app.classifiers.evm_classifier import classify_evm_actions
from app.classifiers.solana_classifier import classify_solana_actions
from app.models.action import Action

MAX_DISPLAY_ACTIONS = 5


def normalize_actions(raw_tx: dict, chain: str) -> list[Action]:
    if chain == "base":
        actions = classify_evm_actions(raw_tx)
    elif chain == "solana":
        actions = classify_solana_actions(raw_tx)
    else:
        return [Action(type="contract_call", primary=True)]

    if not actions:
        return [Action(type="contract_call", primary=True)]

    actions[0].primary = True

    if len(actions) > MAX_DISPLAY_ACTIONS:
        overflow_count = len(actions) - MAX_DISPLAY_ACTIONS + 1
        actions = actions[: MAX_DISPLAY_ACTIONS - 1]
        actions.append(
            Action(
                type="overflow",
                count=overflow_count,
                note=f"and {overflow_count} more actions...",
            )
        )

    return actions
