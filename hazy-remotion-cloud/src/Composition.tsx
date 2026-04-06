import {
  AbsoluteFill, Audio, Video, Series, Sequence,
  useVideoConfig, interpolate, useCurrentFrame, spring, random
} from 'remotion';
import React from 'react';
import { loadFont } from "@remotion/google-fonts/BebasNeue";

const { fontFamily } = loadFont();

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

const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      background: 'radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.60) 100%)',
      pointerEvents: 'none',
    }}
  />
);

const ZoomingVideo: React.FC<{
  url: string;
  effects: EditorEffects;
  clipDuration: number;
  renderSeed: number;
}> = ({ url, effects, clipDuration, renderSeed }) => {
  const frame = useCurrentFrame();
  const stepZoom = spring({ frame, fps: 30, config: { stiffness: 280, damping: 18 } });
  const scale = effects?.zoom ? interpolate(stepZoom, [0, 1], [1, 1.12]) : 1;
  const shakeX =
    frame < 10 && random(url + renderSeed) > 0.5 ? Math.sin(frame * 2) * 12 : 0;

  const opacity =
    effects?.transition === 'fade'
      ? interpolate(
        frame,
        [0, 15, clipDuration - 15, clipDuration],
        [0, 1, 1, 0],
        { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
      )
      : 1;
  const flashOpacity =
    effects?.transition === 'flash'
      ? interpolate(frame, [0, 5], [0.9, 0], { extrapolateRight: 'clamp' })
      : 0;

  return (
    <AbsoluteFill style={{ transform: `scale(${scale}) translateX(${shakeX}px)`, opacity }}>
      <Video src={url} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      <AbsoluteFill style={{ backgroundColor: 'white', opacity: flashOpacity }} />
    </AbsoluteFill>
  );
};

const AnimatedText: React.FC<{ segment: Segment; effects: EditorEffects }> = ({
  segment,
  effects,
}) => {
  const frame = useCurrentFrame();
  const pop = spring({ frame, fps: 30, config: { damping: 12, stiffness: 200 } });
  const isGlitching = segment.text_effect === 'glitch' && frame % 12 > 9;
  const glitchX = isGlitching ? random(frame) * 15 - 7 : 0;

  const chars = segment.text.length;
  const revealed = Math.floor(interpolate(frame, [0, 30], [0, chars], { extrapolateRight: 'clamp' }));
  const displayText = segment.text_effect === 'typewriter' ? segment.text.slice(0, revealed) : segment.text;
  const cursor = segment.text_effect === 'typewriter' && frame % 15 < 7 ? '_' : '';
  const wordCount = displayText.split(' ').length;
  const words = displayText.split(' ').filter(w => w.length > 0);
  const maxCharInWord = words.length > 0 ? Math.max(...words.map((w) => w.length)) : 1;
  const dynamicSize = maxCharInWord > 12 ? 80 : maxCharInWord > 9 ? 95 : wordCount > 2 ? 105 : 125;

  const yPos =
    segment.position === 'top' ? '10%' : segment.position === 'bottom' ? '72%' : '48%';

  const displayWords = displayText.split(' ');

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
          transform:
            segment.text_effect === 'pop' ? `scale(${pop})` : `translateX(${glitchX}px)`,
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: '16px',
          lineHeight: 1.05,
        }}
      >
        {displayWords.map((word, i) => (
          <span
            key={i}
            style={{
              color:
                word.toUpperCase() === segment.highlight_word?.toUpperCase()
                  ? '#FFFFFF'
                  : '#FFD700',
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

function pickSfx(
  sfxUrls: string[],
  segmentIndex: number,
  totalSegments: number,
  textEffect: string
): string | null {
  if (!sfxUrls || sfxUrls.length === 0) return null;

  const find = (keyword: string) =>
    sfxUrls.find((u) => u.toLowerCase().includes(keyword)) ?? null;

  if (segmentIndex === 0) return find('boom') ?? sfxUrls[0];
  if (segmentIndex === totalSegments - 1) return find('riser') ?? sfxUrls[sfxUrls.length - 1];
  if (textEffect === 'glitch') return find('glitch') ?? sfxUrls[segmentIndex % sfxUrls.length];
  if (textEffect === 'pop') return find('pop') ?? sfxUrls[segmentIndex % sfxUrls.length];
  return find('whoosh') ?? sfxUrls[segmentIndex % sfxUrls.length];
}

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
  bgmVolume = 0.12,
  segments,
  effects,
  renderSeed = 0,
}) => {
  const { fps, durationInFrames } = useVideoConfig();
  const framesPerClip = Math.ceil(durationInFrames / (videoUrls?.length || 1));
  const totalSegments = segments?.length ?? 0;

  return (
    <AbsoluteFill style={{ backgroundColor: 'black' }}>
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

      <Vignette />
      <ProgressBar />

      <Audio src={audioUrl} volume={1.0} />

      {bgmUrl && <Audio src={bgmUrl} volume={bgmVolume} loop />}

      {segments?.map((s, i) => {
        const startFrame = Math.round(s.start * fps);
        const duration = Math.round((s.end - s.start) * fps);
        if (duration <= 0) return null;

        const sfxSrc = pickSfx(sfxUrls, i, totalSegments, s.text_effect ?? 'pop');
        const sfxDuration = Math.min(duration, 60);

        return (
          <Sequence key={i} from={startFrame} durationInFrames={duration}>
            <AnimatedText segment={s} effects={effects} />
            {sfxSrc && (
              <Sequence from={0} durationInFrames={sfxDuration}>
                <Audio
                  src={sfxSrc}
                  volume={i === 0 ? 0.55 : i === totalSegments - 1 ? 0.45 : 0.35}
                />
              </Sequence>
            )}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};