-- Re-Mixed audio worker tables. Run once in the Supabase SQL Editor.
-- Safe to re-run. Adds new tables only; nothing existing is changed.
--
--   track_audio_analysis    waveform peaks + loudness   readable for published tracks (and by the owner)
--   track_fingerprints      Chromaprint fingerprints    no client access (worker / service role only)
--   audio_duplicate_matches likely re-uploads           admins only
--
-- The worker writes with the service-role key, which bypasses RLS.

-- ── Waveform + loudness ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.track_audio_analysis (
  track_id        UUID PRIMARY KEY REFERENCES public.tracks(id) ON DELETE CASCADE,
  status          TEXT NOT NULL DEFAULT 'processing'
                  CHECK (status IN ('processing', 'done', 'failed')),
  duration_sec    REAL,
  peaks           SMALLINT[],          -- 0-100, one per slice of the track
  loudness_lufs   REAL,                -- integrated loudness (ITU-R BS.1770)
  error           TEXT,
  worker_version  TEXT,
  analyzed_at     TIMESTAMPTZ,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.track_audio_analysis ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "audio_analysis_readable" ON public.track_audio_analysis;
CREATE POLICY "audio_analysis_readable" ON public.track_audio_analysis
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM public.tracks t
      WHERE t.id = track_id AND (t.status = 'published' OR t.user_id = auth.uid())
    )
  );

-- ── Fingerprints (never exposed to clients) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS public.track_fingerprints (
  track_id      UUID PRIMARY KEY REFERENCES public.tracks(id) ON DELETE CASCADE,
  fingerprint   INTEGER[] NOT NULL,     -- Chromaprint raw values (two's complement)
  duration_sec  REAL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.track_fingerprints ENABLE ROW LEVEL SECURITY;
-- No policies: with RLS on, anon/authenticated can't read or write at all.
REVOKE ALL ON public.track_fingerprints FROM anon, authenticated;

-- ── Duplicate candidates for moderators ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.audio_duplicate_matches (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  track_id          UUID NOT NULL REFERENCES public.tracks(id) ON DELETE CASCADE,  -- the newer upload
  matched_track_id  UUID NOT NULL REFERENCES public.tracks(id) ON DELETE CASCADE,  -- what it matches
  similarity        REAL NOT NULL CHECK (similarity BETWEEN 0 AND 1),
  reviewed          BOOLEAN NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (track_id, matched_track_id)
);

CREATE INDEX IF NOT EXISTS idx_audio_dup_unreviewed
  ON public.audio_duplicate_matches (created_at DESC) WHERE NOT reviewed;

ALTER TABLE public.audio_duplicate_matches ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "audio_duplicates_admin_read" ON public.audio_duplicate_matches;
CREATE POLICY "audio_duplicates_admin_read" ON public.audio_duplicate_matches
  FOR SELECT USING (public.is_admin());

DROP POLICY IF EXISTS "audio_duplicates_admin_update" ON public.audio_duplicate_matches;
CREATE POLICY "audio_duplicates_admin_update" ON public.audio_duplicate_matches
  FOR UPDATE USING (public.is_admin()) WITH CHECK (public.is_admin());
