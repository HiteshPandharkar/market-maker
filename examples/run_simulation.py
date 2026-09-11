"""Run a reproducible synthetic Level 3 order-book simulation."""

from argparse import ArgumentParser

from l3sim.analytics import imbalance, microprice
from l3sim.generator import Generator
from l3sim.simulation import Runner


def simulate(*, events: int, seed: int, levels: int) -> Runner:
    """Return a runner after seeding and simulating an order book."""

    runner = Runner()
    generator = Generator(seed=seed, book=runner.engine.book)

    runner.run(generator.initial_book_events(levels=levels))
    for _ in range(events):
        runner.process(generator.next_event())
    return runner


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=1_000, help="events to simulate (default: 1000)")
    parser.add_argument("--seed", type=int, default=7, help="random seed (default: 7)")
    parser.add_argument("--levels", type=int, default=5, help="initial levels per side (default: 5)")
    args = parser.parse_args()

    if args.events < 0:
        parser.error("--events cannot be negative")
    if args.levels < 1:
        parser.error("--levels must be positive")

    runner = simulate(events=args.events, seed=args.seed, levels=args.levels)
    snapshot = runner.last_snapshot
    assert snapshot is not None  # initial levels always produce snapshots

    book = runner.engine.book
    print(f"events processed : {len(runner.snapshots)}")
    print(f"trades generated : {len(runner.engine.trades)}")
    print(f"resting orders   : {len(book)}")
    print(f"best bid / ask   : {snapshot.best_bid} / {snapshot.best_ask}")
    print(f"mid / spread     : {snapshot.mid_price} / {snapshot.spread}")
    print(f"3-level imbalance: {imbalance(book, levels=3)}")
    print(f"microprice       : {microprice(book)}")


if __name__ == "__main__":
    main()

