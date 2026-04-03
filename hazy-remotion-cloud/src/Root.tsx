import { Composition } from 'remotion';
import { MyComp } from './Composition';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="MyComp"
        component={MyComp}
        durationInFrames={1800}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          videoUrls: ["https://www.w3schools.com/html/mov_bbb.mp4"],
          audioUrl: "https://www.w3schools.com/html/horse.mp3",
          text: "WELCOME TO HAZY CHANEL",
          effects: {
            zoom: true,
            transition: 'fade',
            textStyle: 'bold'
          }
        }}
      />
    </>
  );
};