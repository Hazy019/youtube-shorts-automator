import { AbsoluteFill, Audio, Video, Series, Sequence, useVideoConfig, interpolate, useCurrentFrame, spring, random } from 'remotion';
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
  const progress = interpolate(frame, [0, durationInFrames], [0, 100], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ height: '6px', backgroundColor: 'rgba(255,215,0,0.3)', top: 0 }}>
      <div style={{ width: `${progress}%`, height: '100%', backgroundColor: '#FFD700', boxShadow: '0 0 10px #FFD700' }} />
    </AbsoluteFill>
  );
};

const Vignette: React.FC = () => (
  <AbsoluteFill style={{ 
    background: 'radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.55) 100%)',
    pointerEvents: 'none'
  }} />
);

const ZoomingVideo: React.FC<{ url: string; effects: EditorEffects; clipDuration: number; renderSeed: number }> = ({ url, effects, clipDuration, renderSeed }) => {
  const frame = useCurrentFrame();
  const stepZoom = spring({ frame, fps: 30, config: { stiffness: 280, damping: 18 } });
  const scale = effects?.zoom ? interpolate(stepZoom, [0, 1], [1, 1.12]) : 1;
  const shakeX = (frame < 10 && random(url + renderSeed) > 0.5) ? Math.sin(frame * 2) * 12 : 0;
  const opacity = effects?.transition === 'fade' 
    ? interpolate(frame, [0, 15, clipDuration - 15, clipDuration], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
    : 1;
  const flashOpacity = effects?.transition === 'flash' ? interpolate(frame, [0, 5], [0.9, 0], { extrapolateRight: 'clamp' }) : 0;

  return (
    <AbsoluteFill style={{ transform: `scale(${scale}) translateX(${shakeX}px)`, opacity }}>
      <Video src={url} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      <AbsoluteFill style={{ backgroundColor: 'white', opacity: flashOpacity }} />
    </AbsoluteFill>
  );
};

const AnimatedText: React.FC<{ segment: Segment; effects: EditorEffects }> = ({ segment, effects }) => {
  const frame = useCurrentFrame();
  const pop = spring({ frame, fps: 30, config: { damping: 12, stiffness: 200 } });
  const isGlitching = segment.text_effect === 'glitch' && frame % 12 > 9;
  const glitchX = isGlitching ? random(frame) * 15 - 7 : 0;

  const yPos = segment.position === 'top' ? '12%' : segment.position === 'bottom' ? '75%' : '50%';

  const words = segment.text.split(' ');
  
  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', padding: '0 50px', top: yPos, height: 'auto' }}>
      <h1 style={{
        color: '#FFD700',
        fontSize: '125px',
        textAlign: 'center',
        fontWeight: '900',
        fontFamily: fontFamily,
        textTransform: 'uppercase',
        WebkitTextStroke: '3px #000',
        textShadow: isGlitching ? '4px 0px 0px #0ff, -4px 0px 0px #f0f' : '0px 10px 30px rgba(0,0,0,0.9)',
        transform: segment.text_effect === 'pop' ? `scale(${pop})` : `translateX(${glitchX}px)`,
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        gap: '20px'
      }}>
        {words.map((word, i) => (
          <span key={i} style={{ color: word.toUpperCase() === segment.highlight_word?.toUpperCase() ? '#FFFFFF' : '#FFD700' }}>
            {word}
          </span>
        ))}
      </h1>
    </AbsoluteFill>
  );
};

export const MyComp: React.FC<{ 
  audioUrl: string; 
  videoUrls: string[]; 
  sfxUrls?: string[]; 
  bgmUrl?: string; 
  segments: Segment[]; 
  effects: EditorEffects;
  renderSeed?: number;
}> = ({ audioUrl, videoUrls, sfxUrls, bgmUrl, segments, effects, renderSeed = 0 }) => {
  const { fps, durationInFrames } = useVideoConfig();
  const framesPerClip = Math.ceil(durationInFrames / (videoUrls?.length || 1));

  return (
    <AbsoluteFill style={{ backgroundColor: 'black' }}>
      <Series>
        {videoUrls.map((url, i) => (
          <Series.Sequence key={i} durationInFrames={framesPerClip}>
            <ZoomingVideo url={url} effects={effects} clipDuration={framesPerClip} renderSeed={renderSeed} />
          </Series.Sequence>
        ))}
      </Series>
      
      <Vignette />
      <ProgressBar />

      <Audio src={audioUrl} />
      {bgmUrl && <Audio src={bgmUrl} volume={0.12} loop />}
      
      {segments?.map((s, i) => {
        const startFrame = Math.round(s.start * fps);
        const duration = Math.round((s.end - s.start) * fps);
        if (duration <= 0) return null;

        return (
          <Sequence key={i} from={startFrame} durationInFrames={duration}>
            <AnimatedText segment={s} effects={effects} />
            {sfxUrls && sfxUrls.length > 0 && <Audio src={sfxUrls[i % sfxUrls.length]} volume={0.6} />}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};