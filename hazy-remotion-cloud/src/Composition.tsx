import {
  AbsoluteFill, Audio, OffthreadVideo, Series, Sequence,
  useVideoConfig, interpolate, useCurrentFrame, spring, random
} from 'remotion';
import React from 'react';
import { loadFont } from "@remotion/google-fonts/BebasNeue";

const { fontFamily } = loadFont();

// ── AUDIO VOLUME CONSTANTS ────────────────────────────────────────────────────
// Voiceover at 1.0 is DOMINANT. SFX accent the edit — felt, not heard over VO.
const SFX_VOL_HOOK = 0.18;
const SFX_VOL_CTA  = 0.18;
const SFX_VOL_MID  = 0.13;
// ─────────────────────────────────────────────────────────────────────────────

interface Segment {
  start: number;
  end: number;
  text: string;
  role?: 'hook' | 'stakes' | 'build' | 'payoff' | 'button' | string;
  text_effect?: 'pop' | 'glitch' | 'typewriter' | 'bounce' | 'glow' | 'slide';
  position?: 'top' | 'center' | 'bottom';
  highlight_word?: string;
  visual_query?: string;
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
    <AbsoluteFill style={{ height: '6px', top: 0, backgroundColor: 'rgba(255,215,0,0.20)', zIndex: 10 }}>
      <div style={{ width: `${progress}%`, height: '100%', background: 'linear-gradient(90deg, #FFD700, #FFA500)' }} />
    </AbsoluteFill>
  );
};

// ── Vignette (darkens edges, keeps text readable) ────────────────────────────
const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      background: 'radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.65) 100%)',
      pointerEvents: 'none',
      zIndex: 2,
    }}
  />
);

// ── CRT Scanline Overlay — GAMING ONLY ───────────────────────────────────────
const CRTOverlay: React.FC = () => (
  <AbsoluteFill
    style={{
      background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.10) 2px, rgba(0,0,0,0.10) 4px)',
      pointerEvents: 'none',
      zIndex: 3,
    }}
  />
);

// ── Cyber HUD Overlay — US / Cybersecurity Category ──────────────────────────
const CyberHUDOverlay: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame % 90, [0, 45, 90], [0.35, 0.75, 0.35]);
  return (
    <AbsoluteFill style={{ pointerEvents: 'none', zIndex: 3, opacity }}>
      {/* Corner Tech Reticles */}
      <svg width="100%" height="100%" style={{ position: 'absolute', top: 0, left: 0 }}>
        <path d="M 30,60 L 30,30 L 60,30" fill="none" stroke="#00F0FF" strokeWidth="3" />
        <path d="M 1050,60 L 1050,30 L 1020,30" fill="none" stroke="#00F0FF" strokeWidth="3" opacity="0.7" />
        <path d="M 30,1860 L 30,1890 L 60,1890" fill="none" stroke="#00F0FF" strokeWidth="3" opacity="0.7" />
        <path d="M 1050,1860 L 1050,1890 L 1020,1890" fill="none" stroke="#00F0FF" strokeWidth="3" opacity="0.7" />
      </svg>
    </AbsoluteFill>
  );
};

// ── Cinematic Light Leak flare overlay ────────────────────────────────────────
const CinematicLightLeak: React.FC<{ clipIndex: number }> = ({ clipIndex }) => {
  const frame = useCurrentFrame();
  const xPos = interpolate(frame % 60, [0, 60], [-50, 150]);
  const opacity = interpolate(frame % 60, [0, 30, 60], [0, 0.18, 0]);
  const color = clipIndex % 2 === 0 ? 'rgba(0, 240, 255, 0.25)' : 'rgba(255, 215, 0, 0.25)';

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(circle at ${xPos}% 20%, ${color} 0%, transparent 60%)`,
        pointerEvents: 'none',
        zIndex: 4,
        opacity,
      }}
    />
  );
};

// ── HOOK OVERLAY — Category-Aware ────────────────────────────────────────────
const HookOverlay: React.FC<{ fps: number; category: string }> = ({ fps, category }) => {
  const frame = useCurrentFrame();
  if (frame > 2.5 * fps) return null;

  const opacity = interpolate(frame, [0, 6, 2.4 * fps, 2.5 * fps], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  if (category === 'gaming') {
    const isVisible = frame % 15 < 10;
    return isVisible ? (
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', pointerEvents: 'none', zIndex: 4, top: '-25%' }}>
        <div style={{
          border: '8px solid rgba(255, 30, 30, 0.85)',
          color: 'rgba(255, 30, 30, 0.85)',
          fontSize: '100px',
          fontWeight: '900',
          fontFamily,
          padding: '16px 36px',
          transform: 'rotate(-8deg)',
          opacity,
          textShadow: '0px 0px 15px rgba(255,0,0,0.5)',
          boxShadow: '0 0 20px rgba(255,0,0,0.35) inset, 0 0 20px rgba(255,0,0,0.35)'
        }}>
          CLASSIFIED
        </div>
      </AbsoluteFill>
    ) : null;
  }

  if (category === 'us-centric') {
    return (
      <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'flex-start', pointerEvents: 'none', zIndex: 4, flexDirection: 'column', padding: '0 0 120px 0' }}>
        <div style={{
          backgroundColor: '#CC0000',
          color: '#FFFFFF',
          fontFamily,
          fontSize: '38px',
          fontWeight: '900',
          letterSpacing: '3px',
          padding: '10px 30px',
          opacity,
          textTransform: 'uppercase',
          width: '100%',
          textAlign: 'center',
          boxShadow: '0 4px 20px rgba(0,0,0,0.6)',
        }}>
          BREAKING NEWS
        </div>
        <div style={{
          backgroundColor: '#1a1a1a',
          color: '#FFD700',
          fontFamily,
          fontSize: '28px',
          padding: '8px 30px',
          opacity: opacity * 0.9,
          width: '100%',
          textAlign: 'center',
        }}>
          — THIS ACTUALLY HAPPENED —
        </div>
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{ justifyContent: 'flex-start', alignItems: 'center', pointerEvents: 'none', zIndex: 4, paddingTop: '80px' }}>
      <div style={{
        background: 'linear-gradient(135deg, rgba(0,0,0,0.85) 0%, rgba(20,20,40,0.90) 100%)',
        border: '2px solid #FFD700',
        borderRadius: '8px',
        color: '#FFD700',
        fontFamily,
        fontSize: '32px',
        fontWeight: '900',
        letterSpacing: '4px',
        padding: '12px 36px',
        opacity,
        textTransform: 'uppercase',
        boxShadow: '0 0 20px rgba(255,215,0,0.3)',
      }}>
        ◈ VERIFIED FACT ◈
      </div>
    </AbsoluteFill>
  );
};

// ── Background video clip with dynamic transitions ───────────────────────────
const ZoomingVideo: React.FC<{
  url: string;
  effects: EditorEffects;
  clipDuration: number;
  renderSeed: number;
  clipIndex?: number;
}> = ({ url, effects, clipDuration, renderSeed, clipIndex = 0 }) => {
  const frame = useCurrentFrame();
  
  // PRO MOVE: Alternate Ken Burns direction per clip
  const zoomDirection = clipIndex % 2 === 0 ? 1 : -1;
  const startScale = zoomDirection === 1 ? 1.0 : 1.15;
  const endScale = zoomDirection === 1 ? 1.15 : 1.0;
  
  const scale = effects?.zoom 
    ? interpolate(frame, [0, clipDuration], [startScale, endScale], { extrapolateRight: 'clamp' }) 
    : 1.05;

  const driftDirection = clipIndex % 2 === 0 ? 1 : -1;
  const driftX = interpolate(frame, [0, clipDuration], [0, 25 * driftDirection]);
  const shakeX = frame < 8 && random(url + renderSeed) > 0.5 ? Math.sin(frame * 2) * 6 : 0;

  // Transition handling: Fade vs Flash vs Directional Whip
  const opacity =
    effects?.transition === 'fade'
      ? interpolate(frame, [0, 8, clipDuration - 8, clipDuration], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
      : 1;

  const flashOpacity =
    effects?.transition === 'flash'
      ? interpolate(frame, [0, 4], [0.6, 0], { extrapolateRight: 'clamp' })
      : 0;

  return (
    <AbsoluteFill style={{ transform: `scale(${scale}) translateX(${shakeX + driftX}px)`, opacity }}>
      <AbsoluteFill style={{ backgroundColor: 'black', opacity: 0.15, zIndex: 1 }} />
      <OffthreadVideo
        src={url}
        muted
        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
      />
      <CinematicLightLeak clipIndex={clipIndex} />
      <AbsoluteFill style={{ backgroundColor: 'white', opacity: flashOpacity, zIndex: 5 }} />
    </AbsoluteFill>
  );
};

// ── Caption text with 6 Cycled Animation Archetypes ───────────────────────────
const AnimatedText: React.FC<{ segment: Segment; effects: EditorEffects }> = ({
  segment,
}) => {
  const frame = useCurrentFrame();

  // 1. POP: High-stiffness spring scale
  const popScale = spring({ frame, fps: 30, config: { damping: 12, stiffness: 220 } });

  // 2. BOUNCE: Vertical drop with rubber spring overshoot
  const bounceY = interpolate(
    spring({ frame, fps: 30, config: { damping: 10, stiffness: 180 } }),
    [0, 1],
    [-70, 0],
    { extrapolateRight: 'clamp' }
  );

  // 3. GLITCH: RGB split offset + micro shake
  const isGlitching = segment.text_effect === 'glitch' && frame % 10 > 7;
  const glitchX = isGlitching ? random(frame) * 12 - 6 : 0;
  const factShakeX = segment.text_effect === 'glitch'
    ? interpolate(frame, [0, 4, 8, 12], [6, -6, 3, 0], { extrapolateRight: 'clamp' })
    : 0;

  // 4. TYPEWRITER: Monospace character reveal
  const chars = segment.text.length;
  const revealed = Math.floor(interpolate(frame, [0, 25], [0, chars], { extrapolateRight: 'clamp' }));
  const displayText = segment.text_effect === 'typewriter' ? segment.text.slice(0, revealed) : segment.text;
  const cursor = segment.text_effect === 'typewriter' && frame % 14 < 7 ? '_' : '';

  // 5. GLOW: Pulsing neon cyan/gold outline shadow
  const glowIntensity = interpolate(frame % 24, [0, 12, 24], [10, 30, 10]);

  // 6. SLIDE: Horizontal whip slide with motion blur opacity
  const slideX = interpolate(frame, [0, 6], [-120, 0], { extrapolateRight: 'clamp' });
  const slideOpacity = interpolate(frame, [0, 5], [0, 1], { extrapolateRight: 'clamp' });

  // Dynamic font sizing
  const words = displayText.split(' ').filter(w => w.length > 0);
  const wordCount = words.length;
  const maxCharInWord = words.length > 0 ? Math.max(...words.map(w => w.length)) : 1;
  let dynamicSize = maxCharInWord > 12 ? 80 : maxCharInWord > 9 ? 95 : wordCount > 2 ? 105 : 125;
  if (segment.role === 'hook') {
    dynamicSize = Math.round(dynamicSize * 1.12);
  }

  const yPos = segment.position === 'top' ? '10%' : segment.position === 'bottom' ? '72%' : '48%';

  // Determine transform & style per effect
  let transformStyle = `scale(${popScale})`;
  let opacityStyle = 1;
  let textShadowStyle = '0px 8px 28px rgba(0,0,0,0.98)';

  const effect = segment.text_effect ?? 'pop';

  if (effect === 'bounce') {
    transformStyle = `translateY(${bounceY}px)`;
  } else if (effect === 'glitch') {
    transformStyle = `translateX(${glitchX + factShakeX}px)`;
    textShadowStyle = isGlitching ? '4px 0px 0px #0FF, -4px 0px 0px #F0F' : '0px 8px 28px rgba(0,0,0,0.98)';
  } else if (effect === 'glow') {
    transformStyle = `scale(${popScale})`;
    textShadowStyle = `0 0 ${glowIntensity}px #00F0FF, 0 0 40px rgba(0,240,255,0.6), 0px 8px 28px rgba(0,0,0,0.98)`;
  } else if (effect === 'slide') {
    transformStyle = `translateX(${slideX}px)`;
    opacityStyle = slideOpacity;
  }

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        padding: '0 50px',
        top: yPos,
        maxHeight: '25%', 
        height: 'auto',
        overflow: 'hidden',
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
          textShadow: textShadowStyle,
          transform: transformStyle,
          opacity: opacityStyle,
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
                ? '#FFD700'
                : '#FFFFFF',
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

// ── WordTimestamp interface ───────────────────────────────────────────────────
interface WordTimestamp {
  word: string;
  start: number;     // seconds
  duration: number;  // seconds
}

// ── Karaoke Caption — word-by-word gold highlight ─────────────────────────────
// This is the #1 retention technique used by top Shorts channels.
// Each word turns gold + bold as the narrator speaks it, then fades back.
// A rolling window of ~8 words is always visible at the bottom of the frame.
const KaraokeCaption: React.FC<{ wordTimestamps: WordTimestamp[]; fps: number }> = ({
  wordTimestamps,
  fps,
}) => {
  const frame = useCurrentFrame();
  const currentTime = frame / fps;

  if (!wordTimestamps || wordTimestamps.length === 0) return null;

  // Find the index of the word currently being spoken
  let currentIdx = -1;
  for (let i = 0; i < wordTimestamps.length; i++) {
    if (currentTime >= wordTimestamps[i].start) {
      currentIdx = i;
    } else {
      break;
    }
  }

  if (currentIdx < 0) return null;

  // Show a rolling window: 3 words before + current + 4 words ahead
  const windowStart = Math.max(0, currentIdx - 3);
  const windowEnd   = Math.min(wordTimestamps.length - 1, currentIdx + 4);
  const visible     = wordTimestamps.slice(windowStart, windowEnd + 1);

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'flex-end',
        alignItems: 'center',
        paddingBottom: '28px',
        pointerEvents: 'none',
        zIndex: 6,
      }}
    >
      <div
        style={{
          background: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0.75) 100%)',
          borderRadius: '16px',
          padding: '16px 28px 20px',
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: '10px',
          maxWidth: '95%',
        }}
      >
        {visible.map((w, i) => {
          const absIdx  = windowStart + i;
          const isCurrent = absIdx === currentIdx;
          const isPast    = absIdx < currentIdx;

          // Pulse animation: scale up slightly when word becomes active
          const pulse = isCurrent
            ? spring({ frame: frame - Math.round(w.start * fps), fps, config: { damping: 15, stiffness: 300 } })
            : 1;

          return (
            <span
              key={absIdx}
              style={{
                fontFamily,
                fontSize:   isCurrent ? '52px' : '42px',
                fontWeight: isCurrent ? '900' : isPast ? '600' : '500',
                color:      isCurrent ? '#FFD700' : isPast ? 'rgba(255,255,255,0.45)' : 'rgba(255,255,255,0.80)',
                textTransform: 'uppercase',
                textShadow: isCurrent
                  ? '0 0 20px rgba(255,215,0,0.9), 0 4px 12px rgba(0,0,0,0.9)'
                  : '0 2px 8px rgba(0,0,0,0.7)',
                WebkitTextStroke: isCurrent ? '1px rgba(0,0,0,0.5)' : 'none',
                transform:  `scale(${pulse})`,
                transition: 'color 0.05s, font-size 0.05s',
                lineHeight: 1.1,
              }}
            >
              {w.word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

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
  category?: string;
  wordTimestamps?: WordTimestamp[];
}> = ({
  audioUrl,
  videoUrls,
  sfxUrls = [],
  bgmUrl,
  bgmVolume = 0.12,
  segments,
  effects,
  renderSeed = 0,
  category = 'general',
  wordTimestamps = [],
}) => {
    const { fps, durationInFrames } = useVideoConfig();
    const safeClipCount = Math.max(1, videoUrls?.length || 1);
    const framesPerClip = Math.ceil(durationInFrames / safeClipCount);
    const totalSegments = segments?.length ?? 0;

    return (
      <AbsoluteFill style={{ backgroundColor: 'black' }}>

        {/* Background clips — fast cuts via 10 clips over ~50s */}
        <Series>
          {videoUrls.map((url, i) => (
            <Series.Sequence key={i} durationInFrames={framesPerClip}>
              <ZoomingVideo
                url={url}
                effects={effects}
                clipDuration={framesPerClip}
                renderSeed={renderSeed}
                clipIndex={i}
              />
            </Series.Sequence>
          ))}
        </Series>

        {/* Cinematic overlays */}
        <Vignette />
        {category === 'gaming' && <CRTOverlay />}
        {category === 'us-centric' && <CyberHUDOverlay />}
        <ProgressBar />
        <HookOverlay fps={fps} category={category} />

        {/* Voiceover — always dominant at 1.0 */}
        <Audio src={audioUrl} volume={1.0} />

        {/* BGM — atmosphere layer */}
        {bgmUrl && <Audio src={bgmUrl} volume={bgmVolume} loop />}

        {/* Karaoke captions — word-by-word gold highlight synced to voiceover */}
        <KaraokeCaption wordTimestamps={wordTimestamps} fps={fps} />

        {/* Captions + SFX per segment */}
        {segments?.map((s, i) => {
          const startFrame = Math.round(s.start * fps);
          const duration = Math.round((s.end - s.start) * fps);
          if (duration <= 0) return null;

          const sfxSrc = pickSfx(sfxUrls, i, totalSegments, s.text_effect ?? 'pop');
          const sfxDuration = Math.min(duration, 45);

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