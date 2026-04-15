import {
  AbsoluteFill, Audio, Video, Series, Sequence,
  useVideoConfig, interpolate, useCurrentFrame, spring, random
} from 'remotion';
import React from 'react';
import { loadFont } from "@remotion/google-fonts/BebasNeue";

const { fontFamily } = loadFont();

// ── AUDIO VOLUME CONSTANTS ────────────────────────────────────────────────────
// Reduced from previous values — voiceover at 1.0 is DOMINANT.
// BGM is atmosphere only (set in builder.py: gaming=0.10, general=0.07).
// SFX accent the edit — they should be felt, not heard over the voiceover.
const SFX_VOL_HOOK = 0.28;   // was 0.55 — boom at segment 0
const SFX_VOL_CTA = 0.22;   // was 0.45 — riser at last segment
const SFX_VOL_MID = 0.18;   // was 0.35 — all body segments
// ─────────────────────────────────────────────────────────────────────────────

interface Segment {
  start: number;
  end: number;
  text: string;
  text_effect?: 'pop' | 'glitch' | 'typewriter';
  position?: 'top' | 'center' | 'bottom';
  highlight_word?: string;
}

interface EditorEffects {
  zoom: boolean;
  transition: 'fade' | 'flash' | 'none';
  textStyle: string;
}

// ── Progress bar (gold, 6px, top of frame) ───────────────────────────────────
const ProgressBar: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const progress = interpolate(frame, [0, durationInFrames], [0, 100], {
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill style={{ height: '6px', top: 0, backgroundColor: 'rgba(255,215,0,0.25)' }}>
      <div style={{ width: `${progress}%`, height: '100%', backgroundColor: '#FFD700' }} />
    </AbsoluteFill>
  );
};

// ── Vignette (darkens edges, keeps text readable) ────────────────────────────
const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      background: 'radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.60) 100%)',
      pointerEvents: 'none',
    }}
  />
);

// ── Background video clip ─────────────────────────────────────────────────────
// loop={true}: short Pexels/Pixverse clips repeat instead of freezing on last frame.
// All b-roll is now 9:16 portrait (Pixverse 5 + fixed parkour footage).
// objectFit="cover" fills 1080×1920 without black bars — no distortion on 9:16 source.
const ZoomingVideo: React.FC<{
  url: string;
  effects: EditorEffects;
  clipDuration: number;
  renderSeed: number;
}> = ({ url, effects, clipDuration, renderSeed }) => {
  const frame = useCurrentFrame();
  const stepZoom = spring({ frame, fps: 30, config: { stiffness: 280, damping: 18 } });
  const scale = effects?.zoom ? interpolate(stepZoom, [0, 1], [1, 1.08]) : 1;  // 1.12→1.08: subtler zoom
  const shakeX = frame < 10 && random(url + renderSeed) > 0.5 ? Math.sin(frame * 2) * 8 : 0;  // 12→8px: softer shake

  const opacity =
    effects?.transition === 'fade'
      ? interpolate(
        frame,
        [0, 12, clipDuration - 12, clipDuration],
        [0, 1, 1, 0],
        { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
      )
      : 1;

  const flashOpacity =
    effects?.transition === 'flash'
      ? interpolate(frame, [0, 4], [0.7, 0], { extrapolateRight: 'clamp' })  // 0.9→0.7: softer flash
      : 0;

  return (
    <AbsoluteFill style={{ transform: `scale(${scale}) translateX(${shakeX}px)`, opacity }}>
      {/* loop={true} — prevents freeze on last frame when clip < segment duration */}
      <Video
        src={url}
        muted
        loop
        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
      />
      <AbsoluteFill style={{ backgroundColor: 'white', opacity: flashOpacity }} />
    </AbsoluteFill>
  );
};

// ── Caption text with dynamic sizing + highlight word ────────────────────────
const AnimatedText: React.FC<{ segment: Segment; effects: EditorEffects }> = ({
  segment,
}) => {
  const frame = useCurrentFrame();
  const pop = spring({ frame, fps: 30, config: { damping: 12, stiffness: 200 } });

  const isGlitching = segment.text_effect === 'glitch' && frame % 12 > 9;
  const glitchX = isGlitching ? random(frame) * 15 - 7 : 0;

  // Typewriter effect: reveal characters over 30 frames
  const chars = segment.text.length;
  const revealed = Math.floor(interpolate(frame, [0, 30], [0, chars], { extrapolateRight: 'clamp' }));
  const displayText = segment.text_effect === 'typewriter' ? segment.text.slice(0, revealed) : segment.text;
  const cursor = segment.text_effect === 'typewriter' && frame % 15 < 7 ? '_' : '';

  // Dynamic font size — prevents overflow on long captions
  const words = displayText.split(' ').filter(w => w.length > 0);
  const wordCount = words.length;
  const maxCharInWord = words.length > 0 ? Math.max(...words.map(w => w.length)) : 1;
  const dynamicSize = maxCharInWord > 12 ? 80 : maxCharInWord > 9 ? 95 : wordCount > 2 ? 105 : 125;

  const yPos = segment.position === 'top' ? '10%' : segment.position === 'bottom' ? '72%' : '48%';

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        padding: '0 40px',
        top: yPos,
        height: 'auto',
      }}
    >
      <h1
        style={{
          fontSize: `${dynamicSize}px`,
          textAlign: 'center',
          fontWeight: '900',
          fontFamily,
          textTransform: 'uppercase',
          WebkitTextStroke: '3px #000',
          textShadow: isGlitching
            ? '4px 0px 0px #0ff, -4px 0px 0px #f0f'
            : '0px 8px 24px rgba(0,0,0,0.95)',
          transform: segment.text_effect === 'pop'
            ? `scale(${pop})`
            : `translateX(${glitchX}px)`,
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: '16px',
          lineHeight: 1.05,
        }}
      >
        {displayText.split(' ').map((word, i) => (
          <span
            key={i}
            style={{
              color: word.toUpperCase() === segment.highlight_word?.toUpperCase()
                ? '#FFFFFF'   // highlight word = white
                : '#FFD700',  // all other words = gold
            }}
          >
            {word}
          </span>
        ))}
        {cursor && <span style={{ color: '#FFD700' }}>{cursor}</span>}
      </h1>
    </AbsoluteFill>
  );
};

// ── Context-aware SFX picker ──────────────────────────────────────────────────
function pickSfx(
  sfxUrls: string[],
  segmentIndex: number,
  totalSegments: number,
  textEffect: string,
): string | null {
  if (!sfxUrls || sfxUrls.length === 0) return null;
  const find = (kw: string) => sfxUrls.find(u => u.toLowerCase().includes(kw)) ?? null;

  if (segmentIndex === 0) return find('boom') ?? sfxUrls[0];
  if (segmentIndex === totalSegments - 1) return find('riser') ?? sfxUrls[sfxUrls.length - 1];
  if (textEffect === 'glitch') return find('glitch') ?? sfxUrls[segmentIndex % sfxUrls.length];
  if (textEffect === 'pop') return find('pop') ?? sfxUrls[segmentIndex % sfxUrls.length];
  return find('whoosh') ?? sfxUrls[segmentIndex % sfxUrls.length];
}

// ── Main composition ──────────────────────────────────────────────────────────
export const MyComp: React.FC<{
  audioUrl: string;
  videoUrls: string[];
  sfxUrls?: string[];
  bgmUrl?: string;
  bgmVolume?: number;
  segments: Segment[];
  effects: EditorEffects;
  renderSeed?: number;
}> = ({
  audioUrl,
  videoUrls,
  sfxUrls = [],
  bgmUrl,
  bgmVolume = 0.07,
  segments,
  effects,
  renderSeed = 0,
}) => {
    const { fps, durationInFrames } = useVideoConfig();
    const safeClipCount = Math.max(1, videoUrls?.length || 1);
    const framesPerClip = Math.ceil(durationInFrames / safeClipCount);
    const totalSegments = segments?.length ?? 0;

    return (
      <AbsoluteFill style={{ backgroundColor: 'black' }}>

        {/* Background clips — cross-cut every ~30s with 3 clips */}
        <Series>
          {videoUrls.map((url, i) => (
            <Series.Sequence key={i} durationInFrames={framesPerClip}>
              <ZoomingVideo
                url={url}
                effects={effects}
                clipDuration={framesPerClip}
                renderSeed={renderSeed}
              />
            </Series.Sequence>
          ))}
        </Series>

        {/* Cinematic overlays */}
        <Vignette />
        <ProgressBar />

        {/* Voiceover — always dominant at 1.0 */}
        <Audio src={audioUrl} volume={1.0} />

        {/* BGM — atmosphere only (gaming: 0.10, general: 0.07 set in builder.py) */}
        {bgmUrl && <Audio src={bgmUrl} volume={bgmVolume} loop />}

        {/* Captions + SFX per segment */}
        {segments?.map((s, i) => {
          const startFrame = Math.round(s.start * fps);
          const duration = Math.round((s.end - s.start) * fps);
          if (duration <= 0) return null;

          const sfxSrc = pickSfx(sfxUrls, i, totalSegments, s.text_effect ?? 'pop');
          const sfxDuration = Math.min(duration, 45);  // 60→45 frames: shorter SFX burst

          // Graduated SFX volumes — reduced from previous values
          const sfxVol = i === 0
            ? SFX_VOL_HOOK
            : i === totalSegments - 1
              ? SFX_VOL_CTA
              : SFX_VOL_MID;

          return (
            <Sequence key={i} from={startFrame} durationInFrames={duration}>
              <AnimatedText segment={s} effects={effects} />
              {sfxSrc && (
                <Sequence from={0} durationInFrames={sfxDuration}>
                  <Audio src={sfxSrc} volume={sfxVol} />
                </Sequence>
              )}
            </Sequence>
          );
        })}
      </AbsoluteFill>
    );
  };