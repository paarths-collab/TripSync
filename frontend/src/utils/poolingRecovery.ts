/** Ignore obsolete REST responses after socket events, mutations or screen exit. */
export function createPoolingRecovery<T>(
  fetchState: () => Promise<T>,
  applyState: (state: T) => void,
  onError: (error: unknown) => void,
) {
  let generation = 0;
  let latestRead = 0;
  let mutations = 0;
  let disposed = false;

  const refresh = async () => {
    if (disposed || mutations) return;
    const startedGeneration = generation;
    const read = ++latestRead;
    try {
      const state = await fetchState();
      if (!disposed && !mutations && generation === startedGeneration && read === latestRead) {
        applyState(state);
      }
    } catch (error) {
      if (!disposed && generation === startedGeneration && read === latestRead) onError(error);
    }
  };

  return {
    refresh,
    invalidate() { generation++; },
    async runAction<R>(action: () => Promise<R>): Promise<R> {
      mutations++;
      generation++;
      try {
        return await action();
      } finally {
        mutations--;
        generation++;
        if (!disposed && !mutations) void refresh();
      }
    },
    dispose() { disposed = true; generation++; },
  };
}
