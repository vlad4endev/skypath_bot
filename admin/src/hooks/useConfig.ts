import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { AdminConfig } from '../types';

let cached: AdminConfig | null = null;

export function useConfig() {
  const [config, setConfig] = useState<AdminConfig | null>(cached);
  const [loading, setLoading] = useState(!cached);

  useEffect(() => {
    if (cached) return;
    api
      .config()
      .then((c) => {
        cached = c;
        setConfig(c);
      })
      .finally(() => setLoading(false));
  }, []);

  return { config, loading };
}
