package local.alba;

import android.content.Context;
import android.graphics.*;
import android.graphics.drawable.Drawable;
import android.widget.Button;

/** Small consistent outline icons, drawn natively without emoji fonts. */
final class NativeIcon extends Drawable {
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private String name;private int color;private final int size;
    NativeIcon(Context context,String name,int color,int dp){this.name=name;this.color=color;size=NativeUi.dp(context,dp);setBounds(0,0,size,size);}
    void update(String name,int color){this.name=name;this.color=color;invalidateSelf();}
    private void line(Canvas c,float... points){Path p=new Path();p.moveTo(points[0],points[1]);for(int i=2;i<points.length;i+=2)p.lineTo(points[i],points[i+1]);c.drawPath(p,paint);}
    @Override public void draw(Canvas canvas){
        canvas.save();Rect b=getBounds();canvas.translate(b.left,b.top);canvas.scale(b.width()/24f,b.height()/24f);
        paint.setColor(color);paint.setStrokeWidth(1.7f);paint.setStyle(Paint.Style.STROKE);paint.setStrokeCap(Paint.Cap.ROUND);paint.setStrokeJoin(Paint.Join.ROUND);
        switch(name){
            case "back":line(canvas,14,5,7,12,14,19);line(canvas,7,12,21,12);break;
            case "chevron":line(canvas,9,6,15,12,9,18);break;
            case "down":line(canvas,6,9,12,15,18,9);break;
            case "more":paint.setStyle(Paint.Style.FILL);for(int x=5;x<22;x+=7)canvas.drawCircle(x,12,1.5f,paint);break;
            case "sun":canvas.drawCircle(12,12,4,paint);for(int i=0;i<8;i++){double a=Math.PI*i/4;line(canvas,12+(float)Math.cos(a)*8,12+(float)Math.sin(a)*8,12+(float)Math.cos(a)*10,12+(float)Math.sin(a)*10);}break;
            case "moon":{Path p=new Path();p.moveTo(20,14);p.cubicTo(15,23,2,20,3,11);p.cubicTo(3,6,7,3,10,3);p.cubicTo(7,10,13,17,20,14);canvas.drawPath(p,paint);break;}
            case "book":line(canvas,12,5,12,21);line(canvas,3,3,8,3,12,5,16,3,21,3,21,19,16,19,12,21,8,19,3,19,3,3);break;
            case "pen":line(canvas,15,3,21,9,10,20,3,21,4,14,15,3);line(canvas,13,5,19,11);break;
            case "eraser":line(canvas,16,3,22,9,11,20,6,20,2,16,16,3);line(canvas,8,10,17,19);line(canvas,11,20,22,20);break;
            case "file":case "paper":line(canvas,14,2,5,2,5,22,19,22,19,7,14,2,14,7,19,7);line(canvas,8,12,16,12);line(canvas,8,16,15,16);break;
            case "check":line(canvas,5,12,10,17,20,6);break;
            case "undo":line(canvas,8,3,3,8,8,13);{Path p=new Path();p.moveTo(3,8);p.lineTo(14,8);p.cubicTo(23,8,23,21,14,21);canvas.drawPath(p,paint);}break;
            case "expand":line(canvas,8,3,3,3,3,8);line(canvas,16,3,21,3,21,8);line(canvas,21,16,21,21,16,21);line(canvas,8,21,3,21,3,16);break;
            case "zoom":canvas.drawCircle(10,10,7,paint);line(canvas,15,15,21,21);line(canvas,7,10,13,10);line(canvas,10,7,10,13);break;
            case "send":line(canvas,12,20,12,4);line(canvas,5,11,12,4,19,11);break;
            case "stop":canvas.drawRoundRect(6,6,18,18,2,2,paint);break;
            case "close":line(canvas,6,6,18,18);line(canvas,18,6,6,18);break;
            case "lab":line(canvas,9,2,15,2);line(canvas,10,2,10,9,3,20,5,22,19,22,21,20,14,9,14,2);line(canvas,7,15,17,15);break;
            case "sparkles":line(canvas,12,2,15,9,22,12,15,15,12,22,9,15,2,12,9,9,12,2);break;
            case "brain":{Path p=new Path();p.moveTo(12,5);p.cubicTo(6,0,3,5,4,8);p.cubicTo(0,10,1,15,4,16);p.cubicTo(3,21,9,23,12,19);p.lineTo(12,5);p.cubicTo(18,0,21,5,20,8);p.cubicTo(24,10,23,15,20,16);p.cubicTo(21,21,15,23,12,19);canvas.drawPath(p,paint);break;}
            case "settings":line(canvas,4,6,20,6);line(canvas,4,12,20,12);line(canvas,4,18,20,18);canvas.drawCircle(9,6,2,paint);canvas.drawCircle(15,12,2,paint);canvas.drawCircle(9,18,2,paint);break;
            case "color":paint.setStyle(Paint.Style.FILL);canvas.drawCircle(12,12,8,paint);break;
            default:line(canvas,12,5,12,19);line(canvas,5,12,19,12);
        }canvas.restore();
    }
    @Override public void setAlpha(int alpha){paint.setAlpha(alpha);}
    @Override public void setColorFilter(ColorFilter filter){paint.setColorFilter(filter);}
    @Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
    @Override public int getIntrinsicWidth(){return size;}
    @Override public int getIntrinsicHeight(){return size;}
    static final class IconButton extends Button {
        private final NativeIcon icon;
        IconButton(Context context,String name,String description,int color,Runnable action){
            super(context);icon=new NativeIcon(context,name,color,22);setContentDescription(description);setOnClickListener(v->action.run());
            setMinimumWidth(0);setMinimumHeight(0);setMinWidth(0);setMinHeight(0);setPadding(0,0,0,0);setStateListAnimator(null);
            setBackground(NativeUi.touch(context,Color.TRANSPARENT,22,0));
        }
        void icon(String name,int color){icon.update(name,color);invalidate();}
        @Override protected void onDraw(Canvas canvas){int size=NativeUi.dp(getContext(),22);icon.setBounds((getWidth()-size)/2,(getHeight()-size)/2,(getWidth()+size)/2,(getHeight()+size)/2);icon.draw(canvas);}
    }
}
