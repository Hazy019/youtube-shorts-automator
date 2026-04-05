import { Composition } from 'remotion';
import { MyComp } from './Composition';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="MyComp"
      component={MyComp}
      durationInFrames={900}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{
        videoUrls: ["https://www.w3schools.com/html/mov_bbb.mp4"],
        audioUrl: "https://www.w3schools.com/html/horse.mp3",
        segments: [
            { 
                start: 0, 
                end: 3, 
                text: "v3 Hook", 
                text_effect: "pop", 
                position: "top", 
                highlight_word: "v3" 
            },
            { 
                start: 3, 
                end: 6, 
                text: "Sample Fact", 
                text_effect: "glitch", 
                position: "center", 
                highlight_word: "Fact" 
            }
        ],
        renderSeed: 12345,
        bgmVolume: 0.12,
        effects: { zoom: true, transition: 'flash', textStyle: 'bold' }
      }}
    />
  );
};
