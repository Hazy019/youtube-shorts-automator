import {
  AbsoluteFill, Audio, Video, Series, Sequence, useVideoConfig,
  interpolate, useCurrentFrame, spring, random
} from 'remotion';
import React from 'react';

interface Segment {
  start: number;
  end: number;
  text: string;
  text_effect?: 'pop' | 'glitch' | 'typewriter';
}

interface EditorEffects {
  zoom: boolean;
  transition: 'fade' | 'flash' | 'none';
  textStyle: string;
}

const ZoomingVideo: React.FC<{ url: string; effects: EditorEffects; clipDuration: number }> = ({ url, effects, clipDuration }) => {
  const frame = useCurrentFrame();

  const scale = effects?.zoom ? interpolate(frame, [0, clipDuration], [1, 1.15], { extrapolateRight: 'clamp' }) : 1;

  const shakeX = frame < 8 ? Math.sin(frame * 2) * 15 : 0;
  const shakeY = frame < 8 ? Math.cos(frame * 2.5) * 10 : 0;

  const opacity = effects?.transition === 'fade'
    ? interpolate(frame, [0, 15, clipDuration - 15, clipDuration], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
    : 1;

  const flashOpacity = effects?.transition === 'flash'
    ? interpolate(frame, [0, 4], [0.8, 0], { extrapolateRight: 'clamp' })
    : 0;

  return (
    <AbsoluteFill style={{ transform: `scale(${scale}) translate(${shakeX}px, ${shakeY}px)`, opacity }}>
      <Video src={url} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      {effects?.transition === 'flash' && (
        <AbsoluteFill style={{ backgroundColor: 'white', opacity: flashOpacity }} />
      )}
    </AbsoluteFill>
  );
};

const AnimatedText: React.FC<{ text: string; effectType: string; effects: EditorEffects }> = ({ text, effectType, effects }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const popAnimation = spring({ frame, fps, config: { damping: 14, stiffness: 200, mass: 0.8 } });

  const charsShown = Math.floor(interpolate(frame, [0, 30], [0, text.length], { extrapolateRight: 'clamp' }));
  const typeWriterText = effectType === 'typewriter' ? text.slice(0, charsShown) : text;
  const cursor = effectType === 'typewriter' && frame % 15 < 7 ? '_' : '';

  const isGlitching = effectType === 'glitch' && frame % 10 > 7;
  const glitchX = isGlitching ? random(frame) * 20 - 10 : 0;

  let textShadow = '0px 5px 15px rgba(0,0,0,1), 0px 10px 40px rgba(0,0,0,0.8)';
  if (isGlitching) {
    textShadow = '5px 0px 0px rgba(0,255,255,0.8), -5px 0px 0px rgba(255,0,255,0.8)';
  }

  const baseStyle: React.CSSProperties = {
    color: '#FFD700',
    fontSize: '95px',
    textAlign: 'center',
    fontWeight: effects?.textStyle === 'bold' ? '900' : '500',
    fontFamily: 'Arial, sans-serif',
    textTransform: 'uppercase',
    width: '100%',
    lineHeight: '1.1',
    textShadow: textShadow,
    transform: effectType === 'pop' ? `scale(${popAnimation})` : `translateX(${glitchX}px)`,
  };

  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', padding: '0 80px' }}>
      <h1 style={baseStyle}>
        {effectType === 'typewriter' ? typeWriterText + cursor : text}
      </h1>
    </AbsoluteFill>
  );
};

export const MyComp: React.FC<{ audioUrl: string; videoUrls: string[]; sfxUrls?: string[]; bgmUrl?: string; segments: Segment[]; effects: EditorEffects; }> = ({ audioUrl, videoUrls, sfxUrls, bgmUrl, segments, effects }) => {
  const { fps, durationInFrames } = useVideoConfig();
  const videoCount = videoUrls?.length || 0;
  const framesPerClip = videoCount > 0 ? Math.ceil(durationInFrames / videoCount) : 0;

  return (
    <AbsoluteFill style={{ backgroundColor: 'black' }}>
      <AbsoluteFill>
        {videoCount > 0 ? (
          <Series>
            {videoUrls.map((url, index) => (
              <Series.Sequence key={index} durationInFrames={framesPerClip}>
                <ZoomingVideo url={url} effects={effects} clipDuration={framesPerClip} />
              </Series.Sequence>
            ))}
          </Series>
        ) : null}
      </AbsoluteFill>

      <Audio src={audioUrl} />
      {bgmUrl && <Audio src={bgmUrl} volume={0.12} loop />}

      {segments?.map((segment, index) => {
        const startFrame = Math.round(segment.start * fps);
        const endFrame = Math.round(segment.end * fps);
        const duration = endFrame - startFrame;
        if (duration <= 0) return null;

        return (
          <Sequence key={index} from={startFrame} durationInFrames={duration}>
            <AnimatedText text={segment.text} effectType={segment.text_effect || 'pop'} effects={effects} />

            {sfxUrls && sfxUrls.length > 0 && (
              <Audio src={sfxUrls[index % sfxUrls.length]} volume={0.6} />
            )}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};