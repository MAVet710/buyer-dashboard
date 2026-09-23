/** Change only the homepage operation hash, preserving the router's history entry. */
export function replaceSolutionHash(
  solutionId: string,
  history: Pick<History, "state" | "replaceState">,
): void {
  history.replaceState(
    history.state,
    "",
    `#solution-${encodeURIComponent(solutionId)}`,
  );
}
