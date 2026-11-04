# Roadmap

Open work, most useful first.

## Evidence

- **Problems nobody listed in advance.** The rules checklist matched the agent team on the held-out businesses
  ([docs/baselines.md](docs/baselines.md)), but every planted problem there is one a checklist could name. The next test
  plants kinds of problem the checklist was never written for (a pricing error, broken conversion tracking, affiliates
  claiming sales they didn't cause) and checks which setup catches them.
- **A larger business.** Run the same comparison with three times the data per week, where one prompt can no longer hold
  every tool's output and something has to choose what to look at.
- **Fresh private held-out seeds.** Publishing the eval retired seeds 301–303. New seeds, kept private until scored, give
  a current held-out claim (`evals/team_eval.py --seeds <new> --split heldout`, about $7.50 for three).

## Product

- **The growth lead reads rejection reasons.** A rejected decision's reason (`growth_os/actions/executor.py`) should reach
  the next weekly run, so an idea that was turned down isn't proposed again without new evidence. The single-business
  analyst already does this; the team does not. Changes a prompt, so the team eval has to be re-run.
- **Held-out businesses in the decision deck.** Let the console switch between the showcase business and seeds 301–303.
  Needs the per-decision quarter outcomes recomputed for those three.
- **Shareable deck choices.** Encode the visitor's approve/reject choices in the console URL so a result can be linked.
  The view router already owns the hash (`growth_os/console/template.html`), so both need one router.

## Developer experience

- **A clear error when the API key is missing.** Check `ANTHROPIC_API_KEY` before `growth-os team` or the team eval
  starts; today the failure surfaces inside the specialists' threads.
- **Help per command.** Move `growth_os/cli.py` to argparse subcommands so `growth-os team --help` lists only the team's flags.
