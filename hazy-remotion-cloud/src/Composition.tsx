import {
  AbsoluteFill,
  Audio,
  Video,
  Series,
  useVideoConfig,
  interpolate,
  useCurrentFrame
} from 'remotion';
import React from 'react';

interface EditorEffects {
  zoom: boolean;
  transition: string;
  textStyle: string;
}

export const MyComp: React.FC<{
  audioUrl: string;
  videoUrls: string[];
  text: string;
  effects: EditorEffects;
}> = ({ audioUrl, videoUrls, text, effects }) => {

  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const scale = effects?.zoom
    ? interpolate(frame, [0, durationInFrames], [1, 1.15], {
      extrapolateRight: 'clamp',
    })
    : 1;

  const framesPerClip = Math.ceil(durationInFrames / videoUrls.length);

  return (
    <AbsoluteFill style={{ backgroundColor: 'black' }}>

      <AbsoluteFill style={{ transform: `scale(${scale})` }}>
        <Series>
          {videoUrls.map((url, index) => (
            <Series.Sequence key={index} durationInFrames={framesPerClip}>
              <Video
                src={url}
                muted
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover'
                }}
              />
            </Series.Sequence>
          ))}
        </Series>
      </AbsoluteFill>

      <Audio src={audioUrl} />

      <AbsoluteFill style={{
        justifyContent: 'center',
        alignItems: 'center',
        padding: '0 80px'
      }}>
        <h1
          style={{
            color: '#FFD700',
            fontSize: '90px',
            textAlign: 'center',
            textShadow: '0px 10px 30px rgba(0,0,0,0.8)',
            fontWeight: effects?.textStyle === 'bold' ? '900' : '500',
            fontFamily: 'Arial, sans-serif',
            textTransform: 'uppercase',
            width: '100%',
            lineHeight: '1.2'
          }}
        >
          {text}
        </h1>
      </AbsoluteFill>

    </AbsoluteFill>
  );
};