package local.alba;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.MotionEvent;
import android.view.View;
import org.json.*;

/** Native ink in the notebook's canonical 1000 x 640 coordinate space. */
final class NotebookCanvas extends View {
    final JSONArray strokes;
    private JSONArray points;
    private final String paper;
    private final Runnable changed;
    private final Paint pen=new Paint(Paint.ANTI_ALIAS_FLAG);
    NotebookCanvas(Context context,JSONObject content,Runnable changed) throws Exception {
        super(context);this.changed=changed;this.paper=content.optString("paper","plain");
        JSONObject drawing=content.optJSONObject("drawing");strokes=new JSONArray(drawing==null?"[]":drawing.optJSONArray("strokes").toString());
        setContentDescription("Notebook drawing canvas");setFocusable(true);setBackgroundColor(0xffe8eadb);
    }
    void undo(){if(strokes.length()>0){strokes.remove(strokes.length()-1);changed.run();invalidate();}}
    @Override protected void onDraw(Canvas canvas){super.onDraw(canvas);canvas.save();canvas.scale(getWidth()/1000f,getHeight()/640f);pen.setStrokeWidth(1);pen.setColor(0xffb4bdac);
        if(!paper.equals("plain")){for(int y=40;y<640;y+=40)canvas.drawLine(0,y,1000,y,pen);if(paper.equals("grid")||paper.equals("engineering"))for(int x=40;x<1000;x+=40)canvas.drawLine(x,0,x,640,pen);}
        for(int i=0;i<strokes.length();i++){JSONObject stroke=strokes.optJSONObject(i);if(stroke==null)continue;JSONArray path=stroke.optJSONArray("points");pen.setColor(Color.parseColor(stroke.optString("color","#213a2b")));pen.setStrokeWidth((float)stroke.optDouble("size",3));pen.setStrokeCap(Paint.Cap.ROUND);for(int j=1;j<path.length();j++){JSONArray a=path.optJSONArray(j-1),b=path.optJSONArray(j);canvas.drawLine((float)a.optDouble(0),(float)a.optDouble(1),(float)b.optDouble(0),(float)b.optDouble(1),pen);}}
        canvas.restore();
    }
    @Override public boolean onTouchEvent(MotionEvent event){
        try{float x=Math.max(0,Math.min(1000,event.getX()/getWidth()*1000)),y=Math.max(0,Math.min(640,event.getY()/getHeight()*640));
            if(event.getAction()==MotionEvent.ACTION_DOWN){if(strokes.length()>=500)return false;getParent().requestDisallowInterceptTouchEvent(true);points=new JSONArray();JSONObject stroke=new JSONObject();stroke.put("color","#213a2b");stroke.put("size",3);stroke.put("points",points);strokes.put(stroke);}
            if(points!=null&&points.length()<5000&&(event.getAction()==MotionEvent.ACTION_MOVE||event.getAction()==MotionEvent.ACTION_DOWN)){JSONArray point=new JSONArray();point.put(Math.round(x*100)/100.0);point.put(Math.round(y*100)/100.0);points.put(point);invalidate();}
            if(event.getAction()==MotionEvent.ACTION_UP||event.getAction()==MotionEvent.ACTION_CANCEL){points=null;getParent().requestDisallowInterceptTouchEvent(false);changed.run();performClick();}return true;
        }catch(Exception e){return false;}
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
