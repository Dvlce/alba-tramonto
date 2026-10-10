package local.alba;
import android.content.Context;
import android.graphics.*;
import android.view.MotionEvent;
import android.view.View;
import org.json.*;
import java.util.ArrayDeque;

/** Native ink, vector erasing and two-finger panning in canonical coordinates. */
final class NotebookCanvas extends View {
    final JSONArray strokes;
    float width=3;
    private int color=0xff213a2b;
    private boolean eraser=false,panning=false;
    private JSONArray points;
    private String paper;
    private final Runnable changed;
    private final Paint pen=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final ArrayDeque<String> history=new ArrayDeque<>();
    private float magnification=1,panX=0,panY=0,lastX,lastY,eraseX,eraseY;
    NotebookCanvas(Context context,JSONObject content,Runnable changed) throws Exception {
        super(context);this.changed=changed;paper=content.optString("paper","plain");JSONObject drawing=content.optJSONObject("drawing");JSONArray saved=drawing==null?null:drawing.optJSONArray("strokes");strokes=new JSONArray(saved==null?"[]":saved.toString());
        setContentDescription("Notebook drawing canvas; two fingers to pan");setFocusable(true);setBackgroundColor(NativeUi.PAPER);
    }
    void setEraser(boolean value){eraser=value;}
    boolean isEraser(){return eraser;}
    int inkColor(){return color;}
    void setPaper(String value){paper=value;invalidate();}
    void setColor(int value){color=value;eraser=false;}
    void zoom(){magnification=magnification==1?0:magnification==0?1.5f:magnification>=2?1:2;panX=panY=0;invalidate();}
    void undo(){if(history.isEmpty())return;try{replace(new JSONArray(history.removeLast()));changed.run();invalidate();}catch(Exception ignored){}}
    private void remember(){if(history.size()>=20)history.removeFirst();history.addLast(strokes.toString());}
    private void replace(JSONArray value){while(strokes.length()>0)strokes.remove(strokes.length()-1);for(int i=0;i<value.length();i++)strokes.put(value.opt(i));}
    private float scale(){return magnification==0?Math.min(getWidth()/1000f,getHeight()/640f):Math.max(getWidth()/1000f,getHeight()/640f)*magnification;}
    private float offsetX(){return (getWidth()-1000*scale())/2+panX;}
    private float offsetY(){return (getHeight()-640*scale())/2+panY;}
    @Override protected void onDraw(Canvas canvas){super.onDraw(canvas);float scale=scale();if(scale<=0)return;canvas.save();canvas.translate(offsetX(),offsetY());canvas.scale(scale,scale);canvas.clipRect(0,0,1000,640);canvas.drawColor(NativeUi.PAPER);pen.setStyle(Paint.Style.STROKE);pen.setStrokeWidth(1);pen.setColor(0xffdfe4d7);
        if(!paper.equals("plain")){for(int y=40;y<640;y+=40)canvas.drawLine(0,y,1000,y,pen);if(paper.equals("grid")||paper.equals("engineering"))for(int x=40;x<1000;x+=40)canvas.drawLine(x,0,x,640,pen);}
        for(int i=0;i<strokes.length();i++){JSONObject stroke=strokes.optJSONObject(i);if(stroke==null)continue;JSONArray path=stroke.optJSONArray("points");if(path==null||path.length()==0)continue;try{pen.setColor(Color.parseColor(stroke.optString("color","#213a2b")));}catch(Exception ignored){pen.setColor(0xff213a2b);}pen.setStyle(Paint.Style.STROKE);pen.setStrokeWidth((float)stroke.optDouble("size",3));pen.setStrokeCap(Paint.Cap.ROUND);pen.setStrokeJoin(Paint.Join.ROUND);String tool=stroke.optString("tool","pen");JSONArray a=path.optJSONArray(0),b=path.optJSONArray(path.length()-1);float x=(float)a.optDouble(0),y=(float)a.optDouble(1),bx=(float)b.optDouble(0),by=(float)b.optDouble(1);
            if(tool.equals("text")){pen.setStyle(Paint.Style.FILL);pen.setTextSize((float)stroke.optDouble("text_size",28));pen.setTypeface(Typeface.SERIF);String[] lines=stroke.optString("text").split("\n");for(int j=0;j<lines.length;j++)canvas.drawText(lines[j],x,y+pen.getTextSize()*(j+1),pen);}
            else if(tool.equals("rectangle"))canvas.drawRect(Math.min(x,bx),Math.min(y,by),Math.max(x,bx),Math.max(y,by),pen);
            else if(tool.equals("ellipse"))canvas.drawOval(Math.min(x,bx),Math.min(y,by),Math.max(x,bx),Math.max(y,by),pen);
            else if(path.length()==1){pen.setStyle(Paint.Style.FILL);canvas.drawCircle(x,y,pen.getStrokeWidth()/2,pen);}
            else{Path shape=new Path();shape.moveTo(x,y);for(int j=1;j<path.length();j++){JSONArray point=path.optJSONArray(j);shape.lineTo((float)point.optDouble(0),(float)point.optDouble(1));}canvas.drawPath(shape,pen);}
        }canvas.restore();
    }
    private int pointCount(){int count=0;for(int i=0;i<strokes.length();i++){JSONArray p=strokes.optJSONObject(i).optJSONArray("points");if(p!=null)count+=p.length();}return count;}
    private void erase(float x,float y) throws Exception {
        float radius=Math.max(12,width*2);JSONArray result=new JSONArray();
        for(int i=0;i<strokes.length();i++){JSONObject s=strokes.getJSONObject(i);JSONArray line=s.getJSONArray("points");if(!s.optString("tool","pen").equals("pen")){result.put(s);continue;}JSONArray piece=new JSONArray();float r=radius+(float)s.optDouble("size",3)/2;
            if(line.length()==1){JSONArray p=line.getJSONArray(0);if(Math.hypot(p.optDouble(0)-x,p.optDouble(1)-y)>r)result.put(s);continue;}
            for(int j=1;j<line.length();j++){JSONArray a=line.getJSONArray(j-1),b=line.getJSONArray(j);double ax=a.optDouble(0),ay=a.optDouble(1),dx=b.optDouble(0)-ax,dy=b.optDouble(1)-ay,ox=ax-x,oy=ay-y,aa=dx*dx+dy*dy,bb=2*(ox*dx+oy*dy),cc=ox*ox+oy*oy-r*r,disc=bb*bb-4*aa*cc;java.util.ArrayList<Double> cuts=new java.util.ArrayList<>();cuts.add(0.0);cuts.add(1.0);if(aa>0&&disc>0){for(double t:new double[]{(-bb-Math.sqrt(disc))/(2*aa),(-bb+Math.sqrt(disc))/(2*aa)})if(t>0&&t<1)cuts.add(t);}java.util.Collections.sort(cuts);
                for(int k=1;k<cuts.size();k++){double lo=cuts.get(k-1),hi=cuts.get(k),mid=(lo+hi)/2;if(Math.hypot(ox+dx*mid,oy+dy*mid)<=r){addPiece(result,s,piece);piece=new JSONArray();}else{if(piece.length()==0)piece.put(new JSONArray().put(ax+dx*lo).put(ay+dy*lo));piece.put(new JSONArray().put(ax+dx*hi).put(ay+dy*hi));}}
            }addPiece(result,s,piece);
        }
        int count=0;for(int i=0;i<result.length();i++)count+=result.getJSONObject(i).getJSONArray("points").length();if(result.length()<=500&&count<=50000)replace(result);
    }
    private void addPiece(JSONArray result,JSONObject source,JSONArray points) throws Exception {if(points.length()>0){JSONObject copy=new JSONObject(source.toString());copy.put("points",points);result.put(copy);}}
    @Override public boolean onTouchEvent(MotionEvent event){
        try{int action=event.getActionMasked();if(event.getPointerCount()>1){if(!panning){panning=true;points=null;lastX=(event.getX(0)+event.getX(1))/2;lastY=(event.getY(0)+event.getY(1))/2;}if(action==MotionEvent.ACTION_MOVE){float x=(event.getX(0)+event.getX(1))/2,y=(event.getY(0)+event.getY(1))/2;panX=Math.max(-1000*scale()/2,Math.min(1000*scale()/2,panX+x-lastX));panY=Math.max(-640*scale()/2,Math.min(640*scale()/2,panY+y-lastY));lastX=x;lastY=y;invalidate();}return true;}
            if(panning){if(action==MotionEvent.ACTION_UP||action==MotionEvent.ACTION_CANCEL){panning=false;getParent().requestDisallowInterceptTouchEvent(false);}return true;}
            float x=(event.getX()-offsetX())/scale(),y=(event.getY()-offsetY())/scale();
            if(action==MotionEvent.ACTION_DOWN){if(x<0||x>1000||y<0||y>640||(!eraser&&(strokes.length()>=500||pointCount()>=50000)))return false;getParent().requestDisallowInterceptTouchEvent(true);remember();changed.run();eraseX=x;eraseY=y;if(!eraser){points=new JSONArray();strokes.put(new JSONObject().put("tool","pen").put("color",String.format("#%06x",color&0xffffff)).put("size",width).put("points",points));}}
            x=Math.max(0,Math.min(1000,x));y=Math.max(0,Math.min(640,y));
            if(action==MotionEvent.ACTION_MOVE||action==MotionEvent.ACTION_DOWN){if(eraser){int steps=Math.max(1,(int)Math.ceil(Math.hypot(x-eraseX,y-eraseY)/5));for(int i=1;i<=steps;i++)erase(eraseX+(x-eraseX)*i/steps,eraseY+(y-eraseY)*i/steps);eraseX=x;eraseY=y;}else if(points!=null&&points.length()<5000&&pointCount()<50000)points.put(new JSONArray().put(Math.round(x*100)/100.0).put(Math.round(y*100)/100.0));invalidate();}
            if(action==MotionEvent.ACTION_UP||action==MotionEvent.ACTION_CANCEL){points=null;changed.run();getParent().requestDisallowInterceptTouchEvent(false);performClick();}return true;
        }catch(Exception e){return false;}
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
